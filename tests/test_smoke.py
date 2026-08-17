# tests/test_smoke.py — cobertura mínima: sanitize_html, process/decrement_tags
# e smoke das rotas principais (ver AGENTS.md, "Não há suíte de testes" → agora há).
#
# Rodar:  python -m unittest discover -s tests -v
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(tempfile.mkdtemp(), 'test.db')

from app import app, db, Post, User, Tag, sanitize_html, process_tags, decrement_tags


class BaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_ECHO'] = False
        with app.app_context():
            db.create_all()
            if User.query.filter_by(username='admin_teste').first():
                return  # seed já rodou (setUpClass executa por subclasse)
            admin = User(username='admin_teste', email='admin@teste.com', is_admin=True)
            admin.set_password('senha-forte-123')
            leitor = User(username='leitor', email='leitor@teste.com', is_admin=False)
            leitor.set_password('senha-forte-123')
            db.session.add_all([admin, leitor])
            db.session.commit()

    def login(self, client, username):
        return client.post('/login', data={'username': username, 'password': 'senha-forte-123'})

    def new_post(self, client, title='Poema', tags='2026, cyberpunk'):
        return client.post('/post/new', json={
            'title': title,
            'body_html': '<p>verso<br>verso</p>',
            'body_md': 'verso\nverso',
            'tags': tags,
        })


class SanitizeTest(unittest.TestCase):
    def test_strips_script(self):
        out = sanitize_html('<p>oi</p><script>alert(1)</script>')
        self.assertNotIn('script', out)
        self.assertIn('oi', out)

    def test_strips_style_attribute(self):
        out = sanitize_html('<div style="background:url(evil)">x</div>')
        self.assertNotIn('style', out)

    def test_blocks_javascript_href(self):
        out = sanitize_html('<a href="javascript:alert(1)">x</a>')
        self.assertNotIn('javascript:', out)

    def test_wraps_pre_code(self):
        self.assertTrue(sanitize_html('<p>x</p>').startswith('<pre><code>'))
        already = '<pre><code>x</code></pre>'
        self.assertEqual(sanitize_html(already), already)


class TagsTest(BaseCase):
    def test_process_and_decrement_keep_count(self):
        with app.app_context():
            Tag.query.delete()
            db.session.commit()
            tags = process_tags('2026, cyberpunk')
            self.assertEqual(tags[0]['type'], 'year')   # YYYY vira year
            self.assertEqual(tags[1]['type'], 'genre')  # resto vira genre
            self.assertEqual(Tag.query.filter_by(name='cyberpunk').first().count, 1)
            process_tags('cyberpunk')
            self.assertEqual(Tag.query.filter_by(name='cyberpunk').first().count, 2)
            decrement_tags(tags)
            decrement_tags([{'type': 'genre', 'value': 'cyberpunk'}])
            # zerou: linha removida
            self.assertIsNone(Tag.query.filter_by(name='cyberpunk').first())


class RoutesTest(BaseCase):
    def test_index_e_paginas_publicas(self):
        c = app.test_client()
        for url in ['/', '/login', '/register', '/sobre', '/depoimentos', '/api/tags']:
            self.assertEqual(c.get(url).status_code, 200, url)

    def test_404(self):
        self.assertEqual(app.test_client().get('/nao-existe').status_code, 404)

    def test_security_headers(self):
        r = app.test_client().get('/')
        self.assertEqual(r.headers['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(r.headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn("default-src 'self'", r.headers['Content-Security-Policy'])

    def test_html_lang_ptbr(self):
        self.assertIn('lang="pt-BR"', app.test_client().get('/').get_data(as_text=True))

    def test_leitor_nao_publica(self):
        c = app.test_client()
        self.login(c, 'leitor')
        r = self.new_post(c)
        self.assertEqual(r.status_code, 403)

    def test_admin_publica_e_edita_com_body_md(self):
        c = app.test_client()
        self.login(c, 'admin_teste')
        pid = self.new_post(c).get_json()['post_id']
        with app.app_context():
            p = db.session.get(Post, pid)
            self.assertEqual(p.body_md, 'verso\nverso')
            self.assertIn('verso', p.body_html)
        # editor recebe o Markdown, não o HTML
        page = c.get(f'/post/{pid}/edit').get_data(as_text=True)
        self.assertIn('verso\nverso', page)

    def test_filtro_de_tags_sql_com_substring(self):
        c = app.test_client()
        self.login(c, 'admin_teste')
        self.new_post(c, title='Alvo', tags='cybernetic')
        r = c.get('/api/posts?tags=["cyber"]')  # substring case-insensitive
        titles = [p['title'] for p in r.get_json()]
        self.assertIn('Alvo', titles)
        r = c.get('/api/posts?tags=["nao-existe-isso"]')
        self.assertNotIn('Alvo', [p['title'] for p in r.get_json()])

    def test_view_throttle_por_sessao(self):
        c = app.test_client()
        self.login(c, 'admin_teste')
        pid = self.new_post(c, title='Views').get_json()['post_id']
        anon = app.test_client()
        for _ in range(3):  # 3 refreshes, mesma sessão
            anon.get(f'/post/{pid}')
        with app.app_context():
            self.assertEqual(db.session.get(Post, pid).views, 1)
        app.test_client().get(f'/post/{pid}')  # sessão nova conta
        with app.app_context():
            self.assertEqual(db.session.get(Post, pid).views, 2)

    def test_like_anonimo_toggle(self):
        c = app.test_client()
        self.login(c, 'admin_teste')
        pid = self.new_post(c, title='Curtir').get_json()['post_id']
        anon = app.test_client()
        r = anon.post(f'/post/{pid}/like', json={'visitor_id': 'teste-uuid'})
        self.assertTrue(r.get_json()['liked'])
        r = anon.post(f'/post/{pid}/like', json={'visitor_id': 'teste-uuid'})
        self.assertFalse(r.get_json()['liked'])

    def test_comentario_exige_login(self):
        c = app.test_client()
        self.login(c, 'admin_teste')
        pid = self.new_post(c, title='Comentar').get_json()['post_id']
        r = app.test_client().post(f'/post/{pid}/comment', data={'body': 'oi'})
        self.assertEqual(r.status_code, 302)  # redirect p/ login
        leitor = app.test_client()
        self.login(leitor, 'leitor')
        r = leitor.post(f'/post/{pid}/comment', data={'body': 'lindo'})
        self.assertEqual(r.status_code, 302)  # logado: redirect p/ o post
        with app.app_context():
            post = db.session.get(Post, pid)
            self.assertEqual(post.comments[0].body, 'lindo')


if __name__ == '__main__':
    unittest.main()
