"""Tests for GlobalKnowledge model and get_global_context helper."""

import pytest

from vinosports.core.knowledge import get_global_context
from vinosports.core.models import GlobalKnowledge

pytestmark = pytest.mark.django_db


class TestGlobalKnowledgeModel:
    def test_str_returns_headline(self):
        item = GlobalKnowledge.objects.create(headline="Messi rejoins Barcelona")
        assert str(item) == "Messi rejoins Barcelona"

    def test_ordering_by_sort_order_then_created(self):
        second = GlobalKnowledge.objects.create(headline="Second", sort_order=1)
        first = GlobalKnowledge.objects.create(headline="First", sort_order=0)
        items = list(GlobalKnowledge.objects.all())
        assert items == [first, second]

    def test_inactive_excluded_from_active_filter(self):
        GlobalKnowledge.objects.create(headline="Active", is_active=True)
        GlobalKnowledge.objects.create(headline="Inactive", is_active=False)
        assert GlobalKnowledge.objects.filter(is_active=True).count() == 1


class TestGetGlobalContext:
    def test_empty_when_no_items(self):
        assert get_global_context() == ""

    def test_empty_when_all_inactive(self):
        GlobalKnowledge.objects.create(headline="Nope", is_active=False)
        assert get_global_context() == ""

    def test_headline_only(self):
        GlobalKnowledge.objects.create(headline="Trump declares war on Iran")
        result = get_global_context()
        assert "What's happening in the world right now:" in result
        assert "- Trump declares war on Iran" in result

    def test_headline_with_detail(self):
        GlobalKnowledge.objects.create(
            headline="Codex source code leaked",
            detail="The entire source, available to the public now",
        )
        result = get_global_context()
        assert "- Codex source code leaked" in result
        assert "  The entire source, available to the public now" in result

    def test_multiple_headlines_ordered(self):
        GlobalKnowledge.objects.create(headline="Second", sort_order=1)
        GlobalKnowledge.objects.create(headline="First", sort_order=0)
        result = get_global_context()
        first_pos = result.index("First")
        second_pos = result.index("Second")
        assert first_pos < second_pos

    def test_inactive_items_excluded(self):
        GlobalKnowledge.objects.create(headline="Visible", is_active=True)
        GlobalKnowledge.objects.create(headline="Hidden", is_active=False)
        result = get_global_context()
        assert "Visible" in result
        assert "Hidden" not in result
