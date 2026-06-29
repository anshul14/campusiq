.PHONY: synth deploy deploy-all destroy bootstrap install

install:
	python3 -m venv .venv
	source .venv/bin/activate && pip install -r requirements.txt

bootstrap:
	source .venv/bin/activate && cdk bootstrap

synth:
	source .venv/bin/activate && cdk synth

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