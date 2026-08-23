def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_list_asset(client):
    response = client.post(
        "/assets",
        data={"name": "Pralni stroj", "category": "Bela tehnika", "purchase_price": "499.90"},
    )
    assert response.status_code == 200
    assert "Pralni stroj" in response.text

    page = client.get("/")
    assert page.status_code == 200
    assert "Pralni stroj" in page.text
    assert "499.90" in page.text


def test_rejects_invalid_price(client):
    response = client.post("/assets", data={"name": "Test", "purchase_price": "ni-cena"})
    assert response.status_code == 422

