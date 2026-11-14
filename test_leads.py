import os
os.environ.pop("ANTHROPIC_API_KEY", None)
from leads import kw_match, db, cycle


def test_hiring_post_matches():
    assert kw_match("[Hiring] Need a web developer for Shopify store", "Budget $2k")
    assert kw_match("Looking for someone to redesign our SaaS landing page")


def test_job_board_items_need_only_a_service_keyword():
    assert kw_match("Senior Product Designer", "Remote, contract", hiring_implied=True)
    assert not kw_match("Senior Accountant", "Remote", hiring_implied=True)


def test_seller_and_offtopic_posts_skipped():
    assert not kw_match("[For Hire] Web developer, 5 years exp", "need a project")
    assert not kw_match("[Hiring] Line cook needed", "paid weekly")
    assert not kw_match("Best SEO tools in 2026?", "discussion")
    assert not kw_match("Hiring a lawyer", "my roads are bad")  # 'ads' must be a whole word


def post(i, title):
    return dict(id=i, src="t", title=title, body="", url="u", hiring_implied=False)


def test_cycle_dedupes_and_primes(tmp_path):
    c = db(str(tmp_path / "t.db"))
    hit = post("a", "[Hiring] need a web designer")
    assert cycle(c, [hit], dry=True, prime=True) == []  # first run only records the backlog
    assert cycle(c, [hit], dry=True) == []              # already seen
    assert [p["id"] for p in cycle(c, [post("b", "[Hiring] need a logo"), post("c", "hi")], dry=True)] == ["b"]


def test_discussion_posts_skipped():
    assert not kw_match("How did you get your first customers for your online shop on a small budget?",
                        "Looking for tips, we have no ads")
    assert not kw_match("My competitor SAAS are getting 10+ free trial on autopilot", "seeking advice")
    assert kw_match("Need a web designer for our bakery", "")
    assert kw_match("Can anyone recommend an agency for SEO?", "")
