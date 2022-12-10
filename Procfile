web: python -m bot
release: curl --create-dirs -o $HOME/.postgresql/root.crt -O https://cockroachlabs.cloud/clusters/37e1c071-15d5-4d47-aee2-52ca2d5be9e2/cert && PYTHONPATH=. alembic upgrade head
