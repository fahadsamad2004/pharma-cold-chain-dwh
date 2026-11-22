# Shortcuts (if `make` is not installed, run the docker compose commands directly).
up:        ## build + start everything (first run takes a few minutes)
	docker compose up airflow-init
	docker compose up -d --build
down:      ## stop (keeps your data)
	docker compose down
reset:     ## stop and DELETE all database data (fresh start)
	docker compose down -v
	rm -f warehouse/*.duckdb warehouse/*.wal
	rm -rf warehouse/parquet data/generated/*.csv data/generated/*.json
seed:      ## drop the 3 Phase-1 historical files into the landing folder
	cp data/raw/01_master_data.csv data/raw/05_pharmacy_sales_data.csv data/raw/06_hospital_demand_data.csv data/landing/
logs:      ## follow watcher + API logs
	docker compose logs -f watcher ingest-api
verify:    ## print reconciliation numbers (staging vs warehouse)
	docker compose exec airflow-scheduler python /opt/airflow/scripts/verify_phase1.py
stream:    ## run a 60-second streaming-ingestion simulation (40 events/s)
	docker compose exec airflow-scheduler airflow dags trigger p1_stream_ingest
