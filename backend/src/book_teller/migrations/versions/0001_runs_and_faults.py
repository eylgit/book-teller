"""The first migration: the tables runs and faults.

Written as plain SQL. The classes in tables.py say the same. A test compares
the two, apart from the defaults and the CHECKs.

A migration is history: once it ran on a real database, it is never changed.
A later change of the tables is a new file.
"""

from alembic import op

# The id of this file, and of the file before it. This is the first one.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE runs (
            id              bigint GENERATED ALWAYS AS IDENTITY
                            CONSTRAINT runs_pkey PRIMARY KEY,
            status          text        NOT NULL DEFAULT 'waiting'
                            CONSTRAINT runs_status_check CHECK (status IN (
                                'waiting', 'writing', 'checking', 'done', 'failed'
                            )),
            chapter         text        NOT NULL,
            -- The script, as a JSON list of its sentences.
            -- NULL until the writer has answered.
            script          jsonb,
            -- Why a failed run failed. NULL for every other status.
            failure         text,
            -- The sums over the model calls of the run that answered.
            tokens_in       integer     NOT NULL DEFAULT 0,
            tokens_out      integer     NOT NULL DEFAULT 0,
            thinking_tokens integer     NOT NULL DEFAULT 0,
            model_seconds   double precision NOT NULL DEFAULT 0,
            created_at      timestamptz NOT NULL DEFAULT now(),
            -- When the run became 'done' or 'failed'.
            finished_at     timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE TABLE faults (
            id              bigint GENERATED ALWAYS AS IDENTITY
                            CONSTRAINT faults_pkey PRIMARY KEY,
            run_id          bigint  NOT NULL
                            CONSTRAINT faults_run_id_fkey
                            REFERENCES runs (id) ON DELETE CASCADE,
            -- The place in the checker's list, from 1.
            position        integer NOT NULL,
            -- What the checker said. Sentence 0: no sentence holds the fault.
            sentence        integer NOT NULL,
            kind            text    NOT NULL
                            CONSTRAINT faults_kind_check CHECK (kind IN (
                                'wrong_fact', 'wrong_concept', 'wrong_example',
                                'wrong_conclusion', 'wrong_strength', 'left_out'
                            )),
            paragraph       integer NOT NULL,
            quote           text    NOT NULL,
            reason          text    NOT NULL,
            -- What the guard said. found_in: the paragraph that holds the
            -- quote, or 0 for none.
            found_in        integer NOT NULL,
            sentence_exists boolean NOT NULL,
            -- Also the index for "the faults of this run".
            CONSTRAINT faults_run_id_position_key UNIQUE (run_id, position)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE faults")
    op.execute("DROP TABLE runs")
