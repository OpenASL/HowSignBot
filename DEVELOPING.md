# Developing

## Setting up your local environment

Run the bootstrap script to set up your local environment.

NOTE: If you're not on macOS, you'll need to install [pyenv](https://github.com/pyenv/pyenv) and [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv) manually.

With Docker running:

```
./script/bootstrap
```

Edit `.env` with the proper values.

## Updating dependencies

Re-run the bootstrap script

```
./script/update
```

## Running tests

```
./script/test
```

## Resetting the database

```
DB_RESET=1 SKIP_BOOTSTRAP=1 ./script/update
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
# Prod
heroku logs -a howsign -t
# Staging
heroku logs -a howsign-staging -t
```

## Setting up Zoom webhooks (for participant indicator and auto-closing)

- Go to your app in the [Zoom app dashboard](https://marketplace.zoom.us/user/build)
- Click "Feature"
- Turn on "Event Subscriptions"
- Add a new event subscription. Set the name to "Participant counter" and the destination URL to `https://<app URL>/zoom`
- Enable the following events:
  - End Meeting
  - Participant/Host joined meeting
  - Participant/Host left meeting
- Copy the verification token and set the `ZOOM_HOOK_TOKEN` environment variable in the app's configuration.
