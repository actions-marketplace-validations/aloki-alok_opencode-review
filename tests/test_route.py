import unittest

from helpers import src  # noqa: F401
from route import Settings, route

REPO = 'acme/app'


def pr(number=7, draft=False, head_repo=REPO, user='alice'):
    return {'number': number, 'draft': draft, 'user': {'login': user, 'type': 'User'},
            'head': {'sha': 'h' * 40, 'repo': {'full_name': head_repo} if head_repo else None},
            'base': {'sha': 'b' * 40, 'ref': 'main'}}


def repo(private=True):
    return {'full_name': REPO, 'private': private}


def pr_event(action='opened', **kw):
    return {'action': action, 'pull_request': pr(**kw), 'repository': repo(),
            'sender': {'login': kw.get('user', 'alice'), 'type': 'User'}}


def comment(body, association='MEMBER', user_type='User', on_pr=True):
    issue = {'number': 7, 'title': 't', 'body': ''}
    if on_pr:
        issue['pull_request'] = {'url': 'x'}
    return {'action': 'created', 'issue': issue, 'repository': repo(),
            'comment': {'id': 99, 'body': body, 'author_association': association,
                        'user': {'login': 'bob', 'type': user_type}}}


S = Settings()


class RouteTest(unittest.TestCase):
    def mode(self, name, event, the_pr=None, settings=S, runner='github-hosted'):
        return route(name, event, the_pr, settings, runner).mode

    def test_pull_request_opened_is_review(self):
        e = pr_event()
        self.assertEqual(self.mode('pull_request', e, e['pull_request']), 'review')

    def test_pull_request_review_types(self):
        for action in ('opened', 'synchronize', 'reopened', 'ready_for_review'):
            e = pr_event(action)
            self.assertEqual(self.mode('pull_request', e, e['pull_request']), 'review', action)
        for action in ('closed', 'labeled', 'edited'):
            e = pr_event(action)
            self.assertEqual(self.mode('pull_request', e, e['pull_request']), 'skip', action)

    def test_draft_pr_is_skipped(self):
        e = pr_event(draft=True)
        self.assertEqual(self.mode('pull_request', e, e['pull_request']), 'skip')

    def test_fork_pr_is_skipped(self):
        e = pr_event(head_repo='mallory/app')
        self.assertEqual(self.mode('pull_request', e, e['pull_request']), 'skip')

    def test_deleted_fork_is_skipped(self):
        e = pr_event(head_repo=None)
        self.assertEqual(self.mode('pull_request', e, e['pull_request']), 'skip')

    def test_dependabot_pr_is_skipped(self):
        e = pr_event(user='dependabot[bot]')
        self.assertEqual(self.mode('pull_request', e, e['pull_request']), 'skip')

    def test_member_question_on_pr_is_ask(self):
        j = route('issue_comment', comment('/oc why is this slow?'), pr(), S, 'github-hosted')
        self.assertEqual((j.mode, j.question, j.comment_kind, j.is_pr), ('ask', 'why is this slow?', 'issue', True))

    def test_oc_review_on_pr_is_review(self):
        for body in ('/oc review', '/oc review this', '  /oc   review\nplease'):
            self.assertEqual(self.mode('issue_comment', comment(body), pr()), 'review', body)

    def test_oc_reviewer_is_a_question(self):
        self.assertEqual(self.mode('issue_comment', comment('/oc reviewer?'), pr()), 'ask')

    def test_oc_review_on_issue_is_ask(self):
        self.assertEqual(self.mode('issue_comment', comment('/oc review', on_pr=False)), 'ask')

    def test_trigger_must_be_a_whole_word(self):
        for body in ('/ocx hi', 'hey /oc hi', '/OC hi', 'thanks'):
            self.assertEqual(self.mode('issue_comment', comment(body), pr()), 'skip', body)

    def test_bare_trigger_is_skipped(self):
        self.assertEqual(self.mode('issue_comment', comment('/oc'), pr()), 'skip')

    def test_non_member_comment_is_skipped(self):
        for assoc in ('CONTRIBUTOR', 'NONE', 'FIRST_TIME_CONTRIBUTOR'):
            self.assertEqual(self.mode('issue_comment', comment('/oc hi', association=assoc), pr()), 'skip', assoc)

    def test_bot_comment_is_skipped(self):
        self.assertEqual(self.mode('issue_comment', comment('/oc hi', user_type='Bot'), pr()), 'skip')

    def test_comment_on_fork_pr_is_skipped(self):
        self.assertEqual(self.mode('issue_comment', comment('/oc hi'), pr(head_repo='mallory/app')), 'skip')

    def test_comment_on_draft_pr_is_answered(self):
        self.assertEqual(self.mode('issue_comment', comment('/oc hi'), pr(draft=True)), 'ask')

    def test_review_comment_reply_kind(self):
        e = comment('/oc is this right?')
        del e['issue']
        e['pull_request'] = pr()
        j = route('pull_request_review_comment', e, e['pull_request'], S, 'github-hosted')
        self.assertEqual((j.mode, j.comment_kind, j.number), ('ask', 'review', 7))

    def test_custom_trigger_and_associations(self):
        s = Settings(trigger='/bot', associations=('OWNER',))
        self.assertEqual(self.mode('issue_comment', comment('/bot hi', association='OWNER'), pr(), s), 'ask')
        self.assertEqual(self.mode('issue_comment', comment('/bot hi', association='MEMBER'), pr(), s), 'skip')
        self.assertEqual(self.mode('issue_comment', comment('/oc hi', association='OWNER'), pr(), s), 'skip')

    def test_public_repo_on_self_hosted_is_refused(self):
        e = pr_event()
        e['repository']['private'] = False
        self.assertEqual(self.mode('pull_request', e, e['pull_request'], runner='self-hosted'), 'skip')
        self.assertEqual(self.mode('pull_request', e, e['pull_request'], runner='github-hosted'), 'review')
        allow = Settings(allow_public_self_hosted=True)
        self.assertEqual(self.mode('pull_request', e, e['pull_request'], allow, 'self-hosted'), 'review')

    def test_other_events_are_skipped(self):
        self.assertEqual(self.mode('push', {'repository': repo()}), 'skip')

    def test_every_skip_has_a_reason(self):
        j = route('issue_comment', comment('/oc hi', association='NONE'), pr(), S, 'github-hosted')
        self.assertTrue(j.reason)


if __name__ == '__main__':
    unittest.main()
