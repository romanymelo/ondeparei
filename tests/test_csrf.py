import pytest

from tests.fakes import tracked_catalog

ID = 100088


def client_without_default_origin(make_client):
    c = make_client(tracked_catalog())
    del c.headers["origin"]
    return c


@pytest.mark.parametrize("headers", [{"Origin": "https://evil.com"}, {"Origin": "null"},
                                     {"Referer": "https://evil.com/x"}])
def test_post_from_other_origin_is_refused(make_client, headers):
    r = client_without_default_origin(make_client).post(f"/serie/{ID}/status", data={"status": "want"},
                                                        headers=headers)
    assert r.status_code == 403 and "Pedido recusado" in r.text


def test_post_without_origin_and_referer_is_refused(make_client):
    r = client_without_default_origin(make_client).post(f"/serie/{ID}/status", data={"status": "want"})
    assert r.status_code == 403


def test_same_origin_by_referer_is_accepted(make_client):
    r = client_without_default_origin(make_client).post(
        f"/serie/{ID}/status", data={"status": "want"}, headers={"Referer": f"http://testserver/serie/{ID}"},
        follow_redirects=False)
    assert r.status_code == 303


def test_get_is_never_checked(make_client):
    assert client_without_default_origin(make_client).get(f"/serie/{ID}").status_code == 200
