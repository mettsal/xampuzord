# tests/test_classify.py — texto/linhas, regra curto/longo e apply/revert de tags.
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(tempfile.mkdtemp(), 'test.db')

from app import app, db, Post, User, Tag
from tools.classify import apply_tags
from tools.classify.text import clean_text, length_class, stats


def pre(text):
    return '<pre><code>' + text.replace('&', '&amp;').replace('<', '&lt;') + '</code></pre>'


class TextTest(unittest.TestCase):
    def test_clean_e_contagem(self):
        s = stats(pre('verso um &\nverso <dois>\n\nverso três'))
        self.assertEqual(s['n_lines'], 3)
        self.assertEqual(s['n_stanzas'], 2)
        self.assertIn('verso <dois>', s['text'])

    def test_length_class(self):
        self.assertEqual(length_class(40), 'curto')
        self.assertEqual(length_class(41), 'longo')
        self.assertIsNone(length_class(0))
        self.assertIsNone(length_class(100, [{'type': 'genre', 'value': 'Prosa'}]))
        self.assertEqual(clean_text(None), '')


class ApplyTest(unittest.TestCase):
    def setUp(self):
        with app.app_context():
            db.drop_all()
            db.create_all()
            u = User(username='a', email='a@a.com')
            u.set_password('x')
            db.session.add(u)
            db.session.flush()
            self.visible = Post(title='v', body_html=pre('a'), author_id=u.id, tags=[])
            self.hidden = Post(title='h', body_html=pre('b'), author_id=u.id, tags=[], hidden=True)
            db.session.add_all([self.visible, self.hidden])
            db.session.commit()
            self.ids = (self.visible.id, self.hidden.id)

    def test_dry_run_idempotente_e_revert(self):
        vid, hid = self.ids
        cls = {str(vid): {'length': 'curto', 'theme': 'amor'},
               str(hid): {'length': 'longo', 'theme': None}}
        with app.app_context():
            ledger = {}
            self.assertEqual(apply_tags.apply(cls, ledger), {vid: ['curto', 'amor'], hid: ['longo']})
            self.assertEqual(Tag.query.count(), 0)  # ensaio não grava
            apply_tags.apply(cls, ledger, write=True)
            self.assertEqual(apply_tags.apply(cls, ledger, write=True), {})  # idempotente
            self.assertEqual(db.session.get(Post, vid).tags[0]['value'], 'curto')
            self.assertEqual({t.name: t.count for t in Tag.query}, {'curto': 1, 'amor': 1})  # oculto não conta
            apply_tags.revert(ledger)
            self.assertEqual(Tag.query.count(), 0)
            self.assertEqual(db.session.get(Post, vid).tags, [])


if __name__ == '__main__':
    unittest.main()
