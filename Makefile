.PHONY: up down logs seed test migrate fresh backend-shell

up:            ## build + run the whole stack
	docker compose up --build

down:          ## stop everything
	docker compose down

fresh:         ## wipe the database volume and restart clean
	docker compose down -v && docker compose up --build

logs:
	docker compose logs -f backend

test:          ## run backend tests (sqlite, no postgres needed)
	cd backend && pip install -r requirements.txt && pytest -q

migrate:       ## generate + apply an Alembic migration inside the backend container
	docker compose exec backend sh -c "alembic revision --autogenerate -m 'init' && alembic upgrade head"

backend-shell:
	docker compose exec backend sh
