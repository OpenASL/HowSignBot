# Developing

## Setting up your local environment

Run the bootstrap script to set up your local environment.

NOTE: If you're not on macOS, you'll need to install [pyenv](https://github.com/pyenv/pyenv) and [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv) manually.

```
. script/bootstrap
```

Edit `.env` with the proper values.

## Updating dependencies

Re-run the bootstrap script

```
. script/bootstrap
```

## Running tests

```
. script/test
```

## Releasing

As a pre-requisite, set the `GH_TOKEN` environment variable to a personal access token with repo access.

To release a new version of the bot:

```
. script/deploy
```

This will tag, push, and deploy to production.

## Viewing logs

```
heroku logs -a howsign -t
```
