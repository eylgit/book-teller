"""The job: "do run number N".

A run is a row in the table "runs" (see runs.py). Somebody saved it with its
chapter, and it waits. do_run does the work: it runs the graph of an episode
on that chapter, and saves how far the run is, and then the result or the
failure.

This file knows nothing of the web. Today the web app calls do_run after it
has sent its answer (see main.py). A worker behind a queue can call the same
function.
"""

from langchain_openai import ChatOpenAI
from langgraph.types import RetryPolicy
from pydantic import BaseModel
from sqlalchemy import Engine

from book_teller import runs
from book_teller.episode import RETRY, Ask, Cost, EpisodeState, run_episode
from book_teller.model_call import (
    ModelAnswer,
    ModelCallError,
    ask_model,
    azure_login,
    make_model,
)
from book_teller.settings import read_model_settings
from book_teller.tables import Status

# The reason of a run that failed for something that is not a failed model
# call: a database that went away, or a bug in our own code.
UNEXPECTED = "unexpected error"


def do_run(engine: Engine, run_id: int, ask: Ask, retry: RetryPolicy = RETRY) -> None:
    """Do the run with this number, from "waiting" to "done" or "failed".

    A model call that fails for good is a result: the run is saved as
    failed, with the reason, and no error leaves this function. Anything
    else that goes wrong is saved as failed too, and then the error goes on
    to the caller, so that it shows in the log.

    Raises NoSuchRun, and asks no model, when no run has this number.
    """
    run = runs.read_run(engine, run_id)
    if run is None:
        raise runs.NoSuchRun(run_id)

    # What the model calls have cost so far. When a later step fails, the
    # graph hands nothing back, and this list is what is left.
    costs: list[Cost] = []

    def a_step_ended(step: str, result: EpisodeState) -> None:
        costs.extend(result.get("costs", []))
        if step == "write":
            runs.set_status(engine, run_id, Status.CHECKING)

    runs.set_status(engine, run_id, Status.WRITING)
    try:
        state = run_episode(run.chapter, ask, retry, a_step_ended)
        runs.save_result(
            engine, run_id, state["script"], state["checked"], state["costs"]
        )
    except ModelCallError as error:
        # The reason alone. The words of the library can be very long.
        runs.mark_failed(engine, run_id, error.reason.value, costs)
    except Exception:
        runs.mark_failed(engine, run_id, UNEXPECTED, costs)
        raise


def ask_with(model: ChatOpenAI) -> Ask:
    """The real "ask the model": ask_model, with the model already inside."""

    def ask[Shape: BaseModel](
        instructions: str, text: str, shape: type[Shape]
    ) -> ModelAnswer[Shape]:
        return ask_model(model, instructions, text, shape)

    return ask


def ask_from_environment() -> Ask:
    """The real "ask the model", as the environment variables describe it.

    Raises SettingsError when a setting of the model is missing. It asks
    nobody yet: the login to Azure happens at the first model call.
    """
    return ask_with(make_model(read_model_settings(), azure_login()))
