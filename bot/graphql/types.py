from ariadne import QueryType

from bot.database import store

query = QueryType()


@query.field("meeting")
async def meeting_by_id(root, info, id):
    # TODO: handle DNE better
    zzzzoom_meeting = await store.get_zzzzoom_meeting(id)
    if not zzzzoom_meeting:
        return None
    zoom_meeting = await store.get_zoom_meeting(zzzzoom_meeting["meeting_id"])
    if not zoom_meeting:
        return None
    return {"url": zoom_meeting["join_url"]}


types = [query]
