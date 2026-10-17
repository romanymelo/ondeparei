import pytest
from fastapi.testclient import TestClient

from tests.fakes import TEST_USER, FakeAuth, FakeCatalog, make_detail, make_page, sqlite_stores


@pytest.fixture
def make_client(tmp_path):
    from app.main import create_app

    clients = []

    def _make(fake, db=None, user=TEST_USER):
        auth = FakeAuth({"tok-teste": user} if user else {})
        client = TestClient(create_app(catalog=fake, auth=auth, stores=sqlite_stores(db or tmp_path / "catalogo.db")),
                            headers={"Origin": "http://testserver"})
        if user:
            client.cookies.set("op_acesso", "tok-teste")
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def fake():
    return FakeCatalog(discover=make_page(), search=make_page(), detail=make_detail())


@pytest.fixture
def client(make_client, fake):
    return make_client(fake)
