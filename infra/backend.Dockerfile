FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements-torch.txt backend/requirements.txt ./backend/

RUN pip install --no-cache-dir -r backend/requirements-torch.txt \
    && pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY models ./models
COPY data ./data
COPY infra/render_start.sh ./infra/render_start.sh

# config/ is REQUIRED at runtime, not just for training: backend/state_context.py
# resolves REPO_ROOT/config/{wages_by_state,state_anchors}.yaml on every
# state-wise request (/states, /resolve-location, /simulate-policy, /heatmap).
# Omitting it 500s every one of those routes on the deployed image while the
# container still starts and /health still passes -- so it fails the health
# check silently. Never drop this COPY.
COPY config ./config

# deploy_artifacts/ ships trained weights/fits WITH the image -- Render (and
# any other host building from this repo) has no access to local artifacts,
# and models/artifacts/*, data/processed/* are otherwise gitignored. This
# COPY overlays them onto the exact runtime paths backend/main.py reads.
#
# Ships ALL 79 states (78 priced + Alaska's excluded.json marker), runtime
# files only: stgcn.pt + copula.json + contract.json/excluded.json per state,
# plus weather.parquet + mu_tevi.parquet. Deliberately EXCLUDES each state's
# wage_loss.parquet and anomaly.pkl (~4MB/state, ~310MB total) -- no route
# reads them per-state. That trim is what makes shipping every state cost
# only ~62MB, so a demo can never 503 on whichever state a judge picks, and
# the live /states response can never contradict the Methodology tab's
# "78 priced" table.
COPY deploy_artifacts/models/artifacts/ ./models/artifacts/
COPY deploy_artifacts/data/processed/ ./data/processed/

ENV PYTHONPATH=/app
RUN chmod +x infra/render_start.sh

EXPOSE 8000

CMD ["infra/render_start.sh"]
