import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_check_confirms_app_and_database():
    client = APIClient()

    response = client.get(reverse("core:health"))

    assert response.status_code == 200
    assert response.data == {"status": "ok"}
