.PHONY: synth diff deploy deploy-all destroy bootstrap install diff-db diff-auth diff-storage diff-compute deploy-db deploy-auth deploy-storage deploy-compute

install:
	python3 -m venv .venv
	source .venv/bin/activate && pip install -r requirements.txt

bootstrap:
	source .venv/bin/activate && cdk bootstrap

synth:
	source .venv/bin/activate && cdk synth

diff:
	source .venv/bin/activate && cdk diff --all

diff-db:
	source .venv/bin/activate && cdk diff CampusIQ-*-Database

diff-auth:
	source .venv/bin/activate && cdk diff CampusIQ-*-Auth

diff-storage:
	source .venv/bin/activate && cdk diff CampusIQ-*-Storage

diff-compute:
	source .venv/bin/activate && cdk diff CampusIQ-*-Compute

deploy:
	source .venv/bin/activate && cdk deploy --all

deploy-db:
	source .venv/bin/activate && cdk deploy CampusIQ-*-Database

deploy-auth:
	source .venv/bin/activate && cdk deploy CampusIQ-*-Auth

deploy-storage:
	source .venv/bin/activate && cdk deploy CampusIQ-*-Storage

deploy-compute:
	source .venv/bin/activate && cdk deploy CampusIQ-*-Compute

destroy:
	source .venv/bin/activate && cdk destroy --all