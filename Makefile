# Plant Brain: common commands. Run from the repo root. See JUMPSTART.md for the full walkthrough.
PY ?= python3

.PHONY: help setup data mock app test checks eval semantic deploy streamlit clean
help:
	@echo "setup    install local Python deps (venv recommended)"
	@echo "data     generate synthetic data + verify the golden scenario"
	@echo "mock     build the local mock warehouse (DuckDB + mocked Cortex)"
	@echo "app      run the Streamlit app locally on the mock"
	@echo "test     data verify + checks + smoke test + eval (all offline)"
	@echo "deploy   deploy everything to Snowflake (needs .env, 00_setup.sql done)"
	@echo "streamlit deploy the app to Streamlit in Snowflake (needs snow CLI)"

setup:
	$(PY) -m pip install -r requirements.txt

data:
	$(PY) data_gen/generate.py
	$(PY) data_gen/generate.py --verify

mock: data
	$(PY) -m mocks.warehouse

app: mock
	PB_BACKEND=mock $(PY) -m streamlit run app/streamlit_app.py

checks:
	$(PY) scripts/run_checks.py

test: data
	$(PY) scripts/render_semantic_view.py --check
	$(PY) scripts/run_checks.py
	$(PY) scripts/smoke_test.py
	$(PY) eval/run_eval.py

eval:
	$(PY) eval/run_eval.py --write

semantic:
	$(PY) scripts/render_semantic_view.py

deploy:
	$(PY) scripts/deploy_snowflake.py

streamlit:
	snow streamlit deploy --project app --replace

clean:
	rm -rf data_gen/out/*.csv mocks/plant_brain.duckdb* build/
