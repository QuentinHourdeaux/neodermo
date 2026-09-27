.PHONY: test migration db-upgrade

test:
	.venv/bin/pytest

migration:
	.venv/bin/flask --app neodermo:create_app db migrate -m "$(msg)"

db-upgrade:
	.venv/bin/flask --app neodermo:create_app db upgrade
