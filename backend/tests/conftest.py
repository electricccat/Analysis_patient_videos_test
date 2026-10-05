"""Automatic literature lookup must never access the real network in tests."""
import httpx
import pytest
from backend.app.evidence import patient_search
from backend.app.evidence.pubmed import PubMedSearch


@pytest.fixture(autouse=True)
def offline_automatic_patient_search(monkeypatch):
    def unavailable(request):
        raise httpx.ConnectError('Test network disabled', request=request)
    monkeypatch.setattr(patient_search, 'PubMedSearch',
                        lambda **kwargs: PubMedSearch(transport=httpx.MockTransport(unavailable), **kwargs))
