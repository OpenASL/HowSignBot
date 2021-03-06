import meetings

SECRET = "myprecious"


def test_create_jitsi_meet_deterministic_urls(snapshot):
    name = "Practice...PRACTICE!!!PrAcTice"
    first = meetings.create_jitsi_meet(name, secret=SECRET)
    assert first == snapshot
    second = meetings.create_jitsi_meet(name, secret=SECRET)
    assert first == second

    third = meetings.create_jitsi_meet("practice-practice-practice", secret=SECRET)
    assert first != third
