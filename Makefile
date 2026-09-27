.PHONY: test migration db-upgrade

test:
	.venv/bin/pytest

migration:
	.venv/bin/flask --app neodermo:create_app db migrate -m "$(msg)" --rev-id "$$(.venv/bin/python -c 'from datetime import UTC, datetime; print(datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))')"

db-upgrade:
	.venv/bin/flask --app neodermo:create_app db upgrade
