# Personalize Bootstrap Tooling

**This directory creates real platform accounts with SYNTHETIC (fabricated)
engagement history.** It exists to solve a real cold-start problem: Amazon
Personalize's `User-Personalization` recipe has a hard training minimum —
1,000+ interaction records across 25+ distinct users — that a freshly
deployed CampusIQ institution won't have on day one. Real students haven't
generated real usage yet.

**What's real and what's synthetic, precisely:** the 30 bootstrap student
accounts are genuine Cognito users and genuine DynamoDB `ENROL#` records —
the same kind of real platform account as any other student, just clearly
namespaced (`bootstrap-{cohort}-{NNN}@...`) and torn down after use. Their
*engagement history* — quiz-module interactions, spread across 6 weeks — is
fabricated, because no one has actually used the platform yet. That
distinction is disclosed everywhere it matters: this tooling proves the
Recommendation Lambda → Personalize mechanism works and ranks sensibly for
different gap profiles. It is not evidence of real student outcomes, and no
output from it is presented anywhere in this project as representing real
classroom results.

## What's here, in run order

1. **`provision_bootstrap_students.py`** — creates the 30 real Cognito
   accounts (10 per cohort: `friction`, `inertia`, `balanced`), sets a
   permanent dev-only password, adds each to the `STUDENT` group, enrolls
   each in the target course via a real `ENROL#` DynamoDB record. Writes
   `bootstrap_students.json` (username + real Cognito sub per student) for
   the next script to read.

2. **`generate_bootstrap_dataset.py`** — reads that roster and generates
   `interactions.csv`/`items.csv` sized to clear Personalize's training
   minimum. Three behavioral cohorts with genuinely different engagement
   patterns (not one flat pattern that "proves" nothing): `friction` and
   `inertia` cohorts each show heavy repeat engagement with their matching
   remediation module; `balanced` shows even engagement with no
   concentration. Deterministic (`random.seed(42)`) — rerunning it against
   the same roster reproduces the same dataset, so the generated CSVs
   aren't committed (see `.gitignore`); the script is the artifact.

3. **`provision_and_validate_personalize.py`** — provisions a Personalize
   dataset group, schemas, datasets, imports the CSVs, trains a solution,
   validates via a **batch inference job** — deliberately not a real-time
   campaign, since campaigns bill hourly whether they're serving requests
   or not. Prints per-cohort recommendation results at the end (using the
   real subs and usernames), with the expected pattern spelled out, so the
   output can be checked by eye rather than trusted blindly.

4. **`teardown_personalize.py`** — deletes the Personalize/S3/IAM
   resources from step 3. Requires typing the dataset group name to
   confirm before deleting anything.

5. **`teardown_bootstrap_students.py`** — deletes the 30 Cognito accounts
   and their `ENROL#` records from step 1. Requires typing `yes` to
   confirm. Without this, the bootstrap accounts stay enrolled and will
   inflate `enrolled_count` on `GET /teacher/me/courses` going forward —
   run this once validation evidence is captured.

## Running it

```bash
cd tools/personalize-bootstrap

export COGNITO_USER_POOL_ID=<your pool id>
export DYNAMODB_TABLE_NAME=<your table name>
export COURSE_ID=phys101   # or whichever course you're validating against

python3 provision_bootstrap_students.py
python3 generate_bootstrap_dataset.py
python3 provision_and_validate_personalize.py   # long-running, 30-60+ min for training
# capture the printed batch inference results as evidence, then:
python3 teardown_personalize.py
python3 teardown_bootstrap_students.py
```

Requires AWS credentials configured for the target account/region. The IAM
role `provision_and_validate_personalize.py` creates
(`CampusIQPersonalizeBootstrapRole`) is scoped to S3 read/write on the one
bucket this tooling creates — it's the role Personalize itself assumes to
read training data and write batch output, not a role used to call the
Personalize API.

## For real deployments

Once an institution has genuine student usage — real quiz attempts, real
module engagement from real students — retrain the solution against that
real interaction history instead. Personalize's `User-Personalization`
recipe updates automatically as new interactions stream in; no
re-architecture is needed to move from bootstrap data to real data, just a
retrain against a real dataset once one exists.