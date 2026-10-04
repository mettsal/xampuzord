# tests/test_smoke.py — cobertura mínima: sanitize_html, process/decrement_tags
# e smoke das rotas principais (ver AGENTS.md, "Não há suíte de testes" → agora há).
#
# Rodar:  python -m unittest discover -s tests -v
import os
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(tempfile.mkdtemp(), 'test.db')

import app as app_module
from app import app, db, Post, User, Tag, Comment, Testimonial, sanitize_html, process_tags, decrement_tags


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
        # IP próprio por chamada: /post/new tem limite de 20/h por visitante
        BaseCase._post_seq = getattr(BaseCase, '_post_seq', 0) + 1
        return client.post('/post/new', headers={'CF-Connecting-IP': f'10.77.0.{BaseCase._post_seq}'}, json={
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

    def test_busca_por_titulo_e_conteudo(self):
        # Posts criados direto via ORM para não gastar o rate limit de /login.
        with app.app_context():
            admin_id = User.query.filter_by(username='admin_teste').first().id
            db.session.add_all([
                Post(title='Sonho Elétrico', body_html='<pre><code>nada especial aqui</code></pre>',
                     author_id=admin_id, tags=[{'type': 'genre', 'value': 'sem-relacao'}]),
                Post(title='Sem Relação Nenhuma', body_html='<pre><code>menciona sonho eletrico no corpo</code></pre>',
                     author_id=admin_id, tags=[{'type': 'genre', 'value': 'outra-tag'}]),
                Post(title='Nenhum Dos Dois', body_html='<pre><code>irrelevante</code></pre>',
                     author_id=admin_id, tags=[{'type': 'genre', 'value': 'irrelevante'}]),
            ])
            db.session.commit()

        c = app.test_client()
        r = c.get('/api/posts?tags=["sonho"]')  # casa por título OU conteúdo
        titles = [p['title'] for p in r.get_json()]
        self.assertIn('Sonho Elétrico', titles)
        self.assertIn('Sem Relação Nenhuma', titles)
        self.assertNotIn('Nenhum Dos Dois', titles)

    def test_view_throttle_por_sessao(self):
        c = app.test_client()
        self.login(c, 'admin_teste')
        pid = self.new_post(c, title='Views').get_json()['post_id']
        anon = app.test_client()
        for _ in range(3):  # 3 refreshes, mesma sessão
            anon.get(f'/post/{pid}', follow_redirects=True)
        with app.app_context():
            self.assertEqual(db.session.get(Post, pid).views, 1)
        app.test_client().get(f'/post/{pid}', follow_redirects=True)  # sessão nova conta
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

    def test_feed_rss_e_atom_globais(self):
        c = app.test_client()
        self.login(c, 'admin_teste')
        self.new_post(c, title='Poema do Feed', tags='cyberpunk')

        r = c.get('/feed.xml')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers['Content-Type'], 'application/rss+xml; charset=utf-8')
        body = r.get_data(as_text=True)
        self.assertIn('Poema do Feed', body)
        self.assertIn('verso', body)  # corpo completo, não teaser

        r = c.get('/feed.atom')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers['Content-Type'], 'application/atom+xml; charset=utf-8')
        self.assertIn('Poema do Feed', r.get_data(as_text=True))

    def test_feed_filtrado_por_tag(self):
        c = app.test_client()
        self.login(c, 'admin_teste')
        self.new_post(c, title='Alvo do Feed', tags='matrix-only-tag')
        self.new_post(c, title='Fora do Feed', tags='outra-tag')

        r = c.get('/feed.xml?tag=matrix-only-tag')
        body = r.get_data(as_text=True)
        self.assertIn('Alvo do Feed', body)
        self.assertNotIn('Fora do Feed', body)

    def test_feed_filtrado_por_multiplas_tags(self):
        # Posts criados direto via ORM (não por HTTP) para não gastar o rate
        # limit de /login (10/min) compartilhado com o resto da suíte.
        with app.app_context():
            admin_id = User.query.filter_by(username='admin_teste').first().id
            db.session.add_all([
                Post(title='Tag A', body_html='<p>a</p>', author_id=admin_id,
                     tags=[{'type': 'genre', 'value': 'somente-a'}]),
                Post(title='Tag B', body_html='<p>b</p>', author_id=admin_id,
                     tags=[{'type': 'genre', 'value': 'somente-b'}]),
                Post(title='Nenhuma', body_html='<p>n</p>', author_id=admin_id,
                     tags=[{'type': 'genre', 'value': 'irrelevante'}]),
            ])
            db.session.commit()

        r = app.test_client().get('/feed.xml?tag=somente-a&tag=somente-b')
        body = r.get_data(as_text=True)
        self.assertIn('Tag A', body)
        self.assertIn('Tag B', body)
        self.assertNotIn('Nenhuma', body)

    def test_feed_remove_caractere_ilegal_em_xml_em_vez_de_quebrar(self):
        # \x0b (controle) sobrevive em body_html de import legado (só passa
        # por html.escape, não por sanitize_html) — feedgen só valida isso na
        # hora de serializar o feed inteiro, então precisa ser removido antes.
        with app.app_context():
            admin_id = User.query.filter_by(username='admin_teste').first().id
            db.session.add(Post(title='Poema Com Controle', author_id=admin_id,
                                 body_html='<pre><code>linha\x0bcom controle</code></pre>'))
            db.session.commit()

        c = app.test_client()
        r = c.get('/feed.xml')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Poema Com Controle', r.get_data(as_text=True))

        r = c.get('/feed.atom')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Poema Com Controle', r.get_data(as_text=True))

    def test_feed_pula_post_com_author_orfao_sem_derrubar_o_resto(self):
        with app.app_context():
            admin_id = User.query.filter_by(username='admin_teste').first().id
            db.session.add(Post(title='Poema Bom', body_html='<p>x</p>', author_id=admin_id))
            # Autor descartável (não o admin_teste da fixture) para não
            # quebrar os outros testes da classe ao órfão-izar o post.
            temp = User(username='autor_temporario', email='temp@teste.com', is_admin=True)
            temp.set_password('senha-forte-123')
            db.session.add(temp)
            db.session.commit()
            db.session.add(Post(title='Poema Orfao', body_html='<p>x</p>', author_id=temp.id))
            db.session.commit()
            User.query.filter_by(id=temp.id).delete()
            db.session.commit()

        r = app.test_client().get('/feed.xml')
        body = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('Poema Bom', body)
        self.assertNotIn('Poema Orfao', body)

    def test_feed_links_no_head(self):
        page = app.test_client().get('/').get_data(as_text=True)
        self.assertIn('type="application/rss+xml"', page)
        self.assertIn('type="application/atom+xml"', page)

    def test_post_tem_og_tags_e_botoes_de_compartilhar(self):
        # Post criado direto via ORM (não por HTTP) para não gastar o rate
        # limit de /login (10/min) compartilhado com o resto da suíte.
        with app.app_context():
            admin_id = User.query.filter_by(username='admin_teste').first().id
            post = Post(title='Poema Compartilhavel', body_html='<p>x</p>', author_id=admin_id)
            db.session.add(post)
            db.session.commit()
            pid = post.id

        page = app.test_client().get(f'/post/{pid}', follow_redirects=True).get_data(as_text=True)
        self.assertIn('og:title', page)
        self.assertIn('og:image', page)
        self.assertIn('twitter:card', page)
        self.assertIn('twitter.com/intent/tweet', page)
        self.assertIn('wa.me', page)
        self.assertIn('shareInstagramBtn', page)

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


class SessionLoginMixin:
    def login(self, client, username):
        # Sessão direta: /login tem rate limit (10/min) que a suíte já gasta.
        with app.app_context():
            user_id = User.query.filter_by(username=username).one().id
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True


class AcervoTest(SessionLoginMixin, BaseCase):
    """Painel /admin/acervo: ocultar/reexibir/importar sem perder Tag.count."""

    def setUp(self):
        import acervo
        self.acervo = acervo
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, '2019'))
        with open(os.path.join(self.root, '2019', 'osso-12-03-19.txt'), 'w', encoding='utf-8') as f:
            f.write('osso\nverso <ângulo>\n')
        self._old_root = acervo.ACERVO_ROOT
        acervo.ACERVO_ROOT = __import__('pathlib').Path(self.root)

    def tearDown(self):
        self.acervo.ACERVO_ROOT = self._old_root

    def tag_count(self, name):
        tag = Tag.query.filter_by(name=name).first()
        return tag.count if tag else 0

    def api(self, client, **body):
        return client.post('/api/admin/acervo', json=body)


    def test_painel_exige_admin(self):
        with app.test_client() as c:
            self.login(c, 'leitor')
            self.assertEqual(c.get('/api/admin/acervo').status_code, 403)

    def test_importa_oculta_e_reexibe(self):
        with app.test_client() as c:
            self.login(c, 'admin_teste')
            state = c.get('/api/admin/acervo').get_json()
            entry = next(f for f in state['files'] if f['path'] == '2019/osso-12-03-19.txt')
            self.assertEqual(entry['state'], 'new')

            dry = self.api(c, include=['2019/osso-12-03-19.txt'], dry_run=True).get_json()
            self.assertEqual(len(dry['import']), 1)
            with app.app_context():
                self.assertIsNone(Post.query.filter_by(source_path='2019/osso-12-03-19.txt').first())

            self.api(c, include=['2019/osso-12-03-19.txt'])
            with app.app_context():
                post = Post.query.filter_by(source_path='2019/osso-12-03-19.txt').one()
                post_id, before = post.id, self.tag_count('2019')
                self.assertEqual(post.title, 'osso')
                self.assertEqual(post.created_at.date().isoformat(), '2019-03-12')
                self.assertIn('&lt;ângulo&gt;', post.body_html)

            self.api(c, exclude=['2019/osso-12-03-19.txt'])
            with app.app_context():
                self.assertTrue(db.session.get(Post, post_id).hidden)
                self.assertEqual(self.tag_count('2019'), before - 1)
            self.assertNotIn(b'verso &lt;', c.get('/api/posts').data)
            self.assertNotIn(b'>osso<', c.get('/feed.xml').data)
            with app.test_client() as anon:
                self.assertEqual(anon.get(f'/post/{post_id}').status_code, 404)
            self.assertEqual(c.get(f'/post/{post_id}', follow_redirects=True).status_code, 200)  # admin vê

            # editar post oculto não mexe nas contagens públicas
            c.post(f'/post/{post_id}/edit', json={'title': 'osso', 'body_html': '<p>x</p>', 'tags': '2019'})
            with app.app_context():
                self.assertEqual(self.tag_count('2019'), before - 1)

            self.api(c, include=['2019/osso-12-03-19.txt'])
            with app.app_context():
                self.assertFalse(db.session.get(Post, post_id).hidden)
                self.assertEqual(self.tag_count('2019'), before)


class SlugTest(SessionLoginMixin, BaseCase):
    """URLs com título: /post/<slug>; id e slugs antigos redirecionam (301)."""

    def test_slugify(self):
        from app import slugify
        self.assertEqual(slugify('xampu é o quê não é'), 'xampu-e-o-que-nao-e')
        self.assertEqual(slugify('  EU QUERO OS VIVOS!! '), 'eu-quero-os-vivos')
        self.assertEqual(slugify('Coração, ação'), 'coracao-acao')
        self.assertEqual(slugify('☆'), '')       # sem letras -> poema-<id>
        self.assertEqual(slugify('500'), '')
        self.assertEqual(slugify('new'), 'poema-new')  # /post/new é o editor
        self.assertLessEqual(len(slugify('palavra ' * 40)), 80)

    def test_slug_redirects_e_edicao(self):
        with app.test_client() as c:
            self.login(c, 'admin_teste')
            r = self.new_post(c, title='Ossos de Março').get_json()
            pid = r['post_id']
            self.assertEqual(r['url'], '/post/ossos-de-marco')
            self.assertEqual(c.get('/post/ossos-de-marco').status_code, 200)

            r = c.get(f'/post/{pid}')
            self.assertEqual(r.status_code, 301)
            self.assertTrue(r.headers['Location'].endswith('/post/ossos-de-marco'))

            # mesmo título de novo -> sufixo
            dup = self.new_post(c, title='Ossos de março').get_json()
            self.assertEqual(dup['url'], '/post/ossos-de-marco-2')

            # título editado: slug novo, o antigo continua levando ao post
            c.post(f'/post/{pid}/edit', json={'title': 'Ossos de Abril', 'body_html': '<p>x</p>', 'tags': ''})
            self.assertEqual(c.get('/post/ossos-de-abril').status_code, 200)
            r = c.get('/post/ossos-de-marco')
            self.assertEqual(r.status_code, 301)
            self.assertTrue(r.headers['Location'].endswith('/post/ossos-de-abril'))

            # só caixa/acento mudou: mesma URL, sem alias novo
            c.post(f'/post/{pid}/edit', json={'title': 'ossos de abril', 'body_html': '<p>x</p>', 'tags': ''})
            with app.app_context():
                self.assertEqual(db.session.get(Post, pid).slug, 'ossos-de-abril')

            # voltar ao título original devolve o slug e o alias some
            c.post(f'/post/{pid}/edit', json={'title': 'Ossos de Março', 'body_html': '<p>x</p>', 'tags': ''})
            self.assertEqual(c.get('/post/ossos-de-marco').status_code, 200)
            self.assertEqual(c.get('/post/ossos-de-abril').status_code, 301)

            self.assertEqual(c.get('/post/nao-existe-mesmo').status_code, 404)
            self.assertEqual(c.get('/post/new').status_code, 200)  # editor intacto

    def test_titulo_sem_letras_usa_id(self):
        with app.test_client() as c:
            self.login(c, 'admin_teste')
            r = self.new_post(c, title='☆').get_json()
            self.assertEqual(r['url'], f"/post/poema-{r['post_id']}")
            self.assertEqual(c.get(r['url']).status_code, 200)

    def test_feed_link_slug_e_guid_por_id(self):
        with app.test_client() as c:
            self.login(c, 'admin_teste')
            pid = self.new_post(c, title='Feed Slug', tags='feedslug').get_json()['post_id']
            xml = c.get('/feed.atom?tag=feedslug').get_data(as_text=True)
            self.assertIn('/post/feed-slug', xml)
            self.assertIn(f'<id>http://localhost/post/{pid}</id>', xml)

    def test_post_oculto_por_slug_e_404(self):
        with app.test_client() as c:
            self.login(c, 'admin_teste')
            pid = self.new_post(c, title='Escondido').get_json()['post_id']
        with app.app_context():
            post = db.session.get(Post, pid)
            post.hidden = True
            db.session.commit()
        with app.test_client() as anon:
            self.assertEqual(anon.get('/post/escondido').status_code, 404)
            self.assertEqual(anon.get(f'/post/{pid}').status_code, 404)


class PrelaunchRateLimitTest(SessionLoginMixin, BaseCase):
    """Rate limit por visitante real (CF-Connecting-IP atrás do tunnel)."""

    def make_post(self):
        with app.test_client() as c:
            self.login(c, 'admin_teste')
            return self.new_post(c, title='Rate Limit Alvo').get_json()['post_id']

    def like(self, client, pid, ip, remote='127.0.0.1'):
        return client.post(f'/post/{pid}/like', json={'visitor_id': 'v-' + ip},
                           headers={'CF-Connecting-IP': ip},
                           environ_base={'REMOTE_ADDR': remote})

    def test_leitura_sem_limite(self):
        c = app.test_client()
        codes = {c.get('/', headers={'CF-Connecting-IP': '198.51.100.7'}).status_code for _ in range(60)}
        self.assertEqual(codes, {200})

    def test_contador_por_visitante(self):
        pid = self.make_post()
        c = app.test_client()
        codes = [self.like(c, pid, '203.0.113.1').status_code for _ in range(31)]
        self.assertEqual(codes[:30], [200] * 30)
        self.assertEqual(codes[30], 429)
        # outro visitante não herda o limite do primeiro
        self.assertEqual(self.like(c, pid, '203.0.113.2').status_code, 200)

    def test_header_ignorado_fora_do_loopback(self):
        pid = self.make_post()
        c = app.test_client()
        codes = [self.like(c, pid, f'192.0.2.{i}', remote='10.9.9.9').status_code for i in range(31)]
        self.assertEqual(codes[30], 429)  # header forjado não abre contador novo


class PruneSeedUsersTest(BaseCase):
    def test_remove_so_contas_de_seed_vazias(self):
        with app.app_context():
            for name, email in [('poet_0', 'poet0@example.com'), ('poet_9', 'eu@real.com'),
                                ('poetisa', 'p@example.com')]:
                u = User(username=name, email=email)
                u.set_password('password123')
                db.session.add(u)
            db.session.commit()
        out = app.test_cli_runner().invoke(args=['prune-seed-users']).output
        self.assertIn('1 conta(s)', out)
        with app.app_context():
            self.assertIsNone(User.query.filter_by(username='poet_0').first())
            self.assertIsNotNone(User.query.filter_by(username='poet_9').first())
            self.assertIsNotNone(User.query.filter_by(username='poetisa').first())


class AdminPanelTest(SessionLoginMixin, BaseCase):
    """Painel /admin: posts, views, moderação, usuários, interruptores."""

    def admin(self):
        c = app.test_client()
        self.login(c, 'admin_teste')
        return c

    def make_user(self, name):
        with app.app_context():
            u = User(username=name, email=f'{name}@teste.com')
            u.set_password('senha-forte-123')
            db.session.add(u)
            db.session.commit()
            return u.id

    def test_api_exige_admin(self):
        c = app.test_client()
        self.login(c, 'leitor')
        for url in ('/api/admin/posts', '/api/admin/users', '/api/admin/moderation', '/api/admin/site'):
            self.assertEqual(c.get(url).status_code, 403, url)
        self.assertEqual(c.get('/admin').status_code, 302)

    def test_galeria_editar(self):
        from app import GalleryItem
        with app.app_context():
            admin_id = User.query.filter_by(username='admin_teste').one().id
            item = GalleryItem(title='velho', image_path='uploads/teasers/nao-existe.jpg', author_id=admin_id)
            db.session.add(item)
            db.session.commit()
            gid = item.id
        data = {'title': ' Novo Título ', 'caption': 'acrílica', 'date': '2026-05-15'}
        leitor = app.test_client()
        self.login(leitor, 'leitor')
        leitor.post(f'/galeria/{gid}/edit', data=data)
        with app.app_context():
            self.assertEqual(db.session.get(GalleryItem, gid).title, 'velho')
        c = self.admin()
        self.assertEqual(c.post(f'/galeria/{gid}/edit', data=data).status_code, 302)
        with app.app_context():
            item = db.session.get(GalleryItem, gid)
            self.assertEqual((item.title, item.caption), ('Novo Título', 'acrílica'))
            self.assertEqual(item.created_at.strftime('%Y-%m-%d'), '2026-05-15')
            self.assertEqual(item.image_path, 'uploads/teasers/nao-existe.jpg')
        c.post(f'/galeria/{gid}/edit', data={'title': '  ', 'caption': 'x'})
        with app.app_context():
            self.assertEqual(db.session.get(GalleryItem, gid).title, 'Novo Título')
        self.assertIn('name="date" value="2026-05-15"', c.get('/galeria').get_data(as_text=True))

    def test_titulo_inline_e_views(self):
        c = self.admin()
        pid = self.new_post(c, title='Painel Antigo', tags='paineltag').get_json()['post_id']
        r = c.patch(f'/api/admin/posts/{pid}', json={'title': '  Painel   Novo '})
        self.assertEqual(r.get_json()['slug'], 'painel-novo')
        self.assertEqual(r.get_json()['title'], 'Painel Novo')
        self.assertEqual(c.get('/post/painel-antigo').status_code, 301)
        self.assertEqual(c.patch(f'/api/admin/posts/{pid}', json={'title': '   '}).status_code, 400)

        with app.app_context():
            db.session.get(Post, pid).views = 7
            db.session.commit()
        c.post(f'/api/admin/posts/{pid}/views/reset')
        with app.app_context():
            self.assertEqual(db.session.get(Post, pid).views, 0)
            db.session.get(Post, pid).views = 3
            db.session.commit()
        self.assertEqual(c.post('/api/admin/views/reset', json={}).status_code, 400)
        self.assertEqual(c.post('/api/admin/views/reset', json={'confirm': 'zerar'}).status_code, 200)
        with app.app_context():
            self.assertEqual(db.session.query(db.func.sum(Post.views)).scalar() or 0, 0)

    def test_ocultar_pelo_painel_mantem_tags(self):
        c = self.admin()
        pid = self.new_post(c, title='Painel Oculto', tags='ocultotag').get_json()['post_id']
        c.patch(f'/api/admin/posts/{pid}', json={'hidden': True})
        with app.app_context():
            self.assertIsNone(Tag.query.filter_by(name='ocultotag').first())
        rows = c.get('/api/admin/posts').get_json()
        self.assertTrue(next(r for r in rows if r['id'] == pid)['hidden'])
        c.patch(f'/api/admin/posts/{pid}', json={'hidden': False})
        with app.app_context():
            self.assertEqual(Tag.query.filter_by(name='ocultotag').one().count, 1)

    def test_moderacao(self):
        c = self.admin()
        pid = self.new_post(c, title='Moderado').get_json()['post_id']
        c.post(f'/post/{pid}/comment', data={'body': 'spam spam'})
        c.post('/depoimentos', data={'body': 'oi guestbook'})
        data = c.get('/api/admin/moderation').get_json()
        comment = next(x for x in data['comments'] if x['body'] == 'spam spam')
        self.assertEqual(comment['post']['url'], '/post/moderado')
        testimonial = next(x for x in data['testimonials'] if x['body'] == 'oi guestbook')
        self.assertEqual(c.delete(f"/api/admin/comments/{comment['id']}").status_code, 200)
        self.assertEqual(c.delete(f"/api/admin/testimonials/{testimonial['id']}").status_code, 200)
        data = c.get('/api/admin/moderation').get_json()
        self.assertFalse(any(x['body'] == 'spam spam' for x in data['comments']))

    def test_bloquear_derruba_sessao_e_login(self):
        uid = self.make_user('bloqueavel')
        vitima = app.test_client()
        self.login(vitima, 'bloqueavel')
        self.assertEqual(vitima.post('/depoimentos', data={'body': 'antes'}).status_code, 302)
        c = self.admin()
        self.assertTrue(c.patch(f'/api/admin/users/{uid}', json={'banned': True}).get_json()['is_banned'])
        # sessão antiga caiu: depoimento agora pede login
        r = vitima.post('/depoimentos', data={'body': 'depois'})
        self.assertIn('/login', r.headers['Location'])
        r = app.test_client().post('/login', data={'username': 'bloqueavel', 'password': 'senha-forte-123'},
                                   headers={'CF-Connecting-IP': '198.51.100.40'}, follow_redirects=True)
        self.assertIn('bloqueado', r.get_data(as_text=True))

    def test_apagar_usuario_leva_o_que_escreveu(self):
        uid = self.make_user('apagavel')
        u = app.test_client()
        self.login(u, 'apagavel')
        u.post('/depoimentos', data={'body': 'vou sumir'})
        c = self.admin()
        r = c.delete(f'/api/admin/users/{uid}').get_json()
        self.assertEqual(r['testimonials'], 1)
        with app.app_context():
            self.assertIsNone(db.session.get(User, uid))
        with app.app_context():
            admin_id = User.query.filter_by(username='admin_teste').one().id
        self.assertEqual(c.delete(f'/api/admin/users/{admin_id}').status_code, 400)

    def test_interruptores(self):
        c = self.admin()
        pid = self.new_post(c, title='Porta Fechada').get_json()['post_id']
        site = c.patch('/api/admin/site', json={'comments_open': False, 'testimonials_open': False,
                                                'registration_open': False}).get_json()
        self.assertFalse(any(sw['on'] for sw in site['switches']))
        self.assertEqual(c.patch('/api/admin/site', json={'nao_existe': True}).status_code, 400)
        try:
            c.post(f'/post/{pid}/comment', data={'body': 'fechado?'})
            c.post('/depoimentos', data={'body': 'fechado?'})
            app.test_client().post('/register', data={'username': 'portafechada', 'email': 'p@f.com',
                                                      'password': 'senha-forte-123'},
                                   headers={'CF-Connecting-IP': '198.51.100.41'})
            self.assertIn('Comentários fechados', c.get('/post/porta-fechada').get_data(as_text=True))
            self.assertIn('Cadastros fechados', app.test_client().get('/register').get_data(as_text=True))
            with app.app_context():
                self.assertEqual(Comment.query.filter_by(body='fechado?').count(), 0)
                self.assertEqual(Testimonial.query.filter_by(body='fechado?').count(), 0)
                self.assertIsNone(User.query.filter_by(username='portafechada').first())
        finally:
            c.patch('/api/admin/site', json={'comments_open': True, 'testimonials_open': True,
                                             'registration_open': True})


class CaptchaTest(BaseCase):
    def register(self, ip, **extra):
        data = {'username': f'u{ip.replace(".", "")}', 'email': f'{ip}@x.com', 'password': 'senha-forte-123'}
        data.update(extra)
        app.test_client().post('/register', data=data, headers={'CF-Connecting-IP': ip})
        with app.app_context():
            return User.query.filter_by(username=data['username']).first() is not None

    def test_honeypot(self):
        self.assertFalse(self.register('198.51.100.50', website='http://spam'))
        self.assertTrue(self.register('198.51.100.51'))

    def test_turnstile_quando_configurado(self):
        import app as app_module
        os.environ.update(TURNSTILE_SITE_KEY='site', TURNSTILE_SECRET_KEY='secret')
        original = app_module.verify_turnstile
        try:
            self.assertIn('cf-turnstile', app.test_client().get('/register').get_data(as_text=True))
            app_module.verify_turnstile = lambda token: False
            self.assertFalse(self.register('198.51.100.52'))
            app_module.verify_turnstile = lambda token: token == 'ok'
            self.assertTrue(self.register('198.51.100.53', **{'cf-turnstile-response': 'ok'}))
        finally:
            app_module.verify_turnstile = original
            del os.environ['TURNSTILE_SITE_KEY'], os.environ['TURNSTILE_SECRET_KEY']


class ShareCardTest(SessionLoginMixin, BaseCase):
    """Cartão de compartilhamento (og:image) com o poema inteiro."""

    def test_wrap_sempre_progride(self):
        # regressão: linha longa sem espaços fazia _wrap girar para sempre
        import cards
        for width in (8, 9, 20, 77):
            for line in ('a' * 500, 'a ' + 'b' * 300, '     ' + 'x' * 200, 'palavra ' * 80, 'ab ' * 100):
                out = cards._wrap([line], width)
                self.assertTrue(all(len(l) <= width for l in out))
                self.assertEqual(''.join(''.join(out).split()), ''.join(line.split()))

    def test_verso_inteiro_tem_prioridade(self):
        import cards
        curto = ['verso curto'] * 12
        size, cols, whole = cards.fit(curto, 944, 416)
        self.assertEqual((cols, whole), (1, True))
        self.assertGreaterEqual(size, cards.READABLE)
        size, cols, whole = cards.fit(['linha'] * 5000, 944, 416)
        self.assertFalse(whole)

    def test_rota_do_cartao(self):
        import io
        import cards
        from PIL import Image
        old_dir = app_module.CARD_CACHE_DIR
        app_module.CARD_CACHE_DIR = __import__('pathlib').Path(tempfile.mkdtemp())
        try:
            c = app.test_client()
            self.login(c, 'admin_teste')
            pid = self.new_post(c, title='Cartão do Poema').get_json()['post_id']
            r = c.get('/post/cartao-do-poema/card.png')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.mimetype, 'image/png')
            self.assertEqual(Image.open(io.BytesIO(r.data)).size, (1200, 630))
            page = c.get('/post/cartao-do-poema').get_data(as_text=True)
            self.assertIn('/post/cartao-do-poema/card.png', page)

            before = sorted(f.name for f in app_module.CARD_CACHE_DIR.iterdir())
            c.get('/post/cartao-do-poema/card.png')  # cache: não gera outro arquivo
            self.assertEqual(sorted(f.name for f in app_module.CARD_CACHE_DIR.iterdir()), before)
            c.post(f'/post/{pid}/edit', json={'title': 'Cartão do Poema', 'body_html': '<p>outro</p>', 'tags': ''})
            c.get('/post/cartao-do-poema/card.png')
            after = sorted(f.name for f in app_module.CARD_CACHE_DIR.iterdir())
            self.assertEqual(len(after), 1)       # versão antiga foi apagada
            self.assertNotEqual(after, before)    # hash mudou com o texto

            c.patch(f'/api/admin/posts/{pid}', json={'hidden': True})
            self.assertEqual(app.test_client().get('/post/cartao-do-poema/card.png').status_code, 404)
        finally:
            app_module.CARD_CACHE_DIR = old_dir

    def test_robots_e_sitemap(self):
        c = app.test_client()
        self.login(c, 'admin_teste')
        self.new_post(c, title='No Sitemap')
        hid = self.new_post(c, title='Fora do Sitemap').get_json()['post_id']
        c.patch(f'/api/admin/posts/{hid}', json={'hidden': True})
        robots = c.get('/robots.txt').get_data(as_text=True)
        self.assertIn('Disallow: /admin', robots)
        self.assertIn('/sitemap.xml', robots)
        xml = c.get('/sitemap.xml').get_data(as_text=True)
        self.assertIn('/post/no-sitemap</loc>', xml)
        self.assertNotIn('fora-do-sitemap', xml)
        self.assertIn('og-default.png', c.get('/sobre').get_data(as_text=True))


class SobreEditTest(SessionLoginMixin, BaseCase):
    def setUp(self):
        self._orig = app_module.SOBRE_FILE
        app_module.SOBRE_FILE = Path(tempfile.mkdtemp()) / 'sobre.html'

    def tearDown(self):
        app_module.SOBRE_FILE = self._orig

    def test_only_admin_edits_and_html_is_sanitized(self):
        anon = app.test_client()
        self.assertIn(anon.post('/sobre/edit', data={'html': '<p>x</p>'}).status_code, (302, 401))
        self.assertFalse(app_module.SOBRE_FILE.exists())

        leitor = app.test_client()
        self.login(leitor, 'leitor')
        leitor.post('/sobre/edit', data={'html': '<p>x</p>'})
        self.assertFalse(app_module.SOBRE_FILE.exists())

        admin = app.test_client()
        self.login(admin, 'admin_teste')
        admin.post('/sobre/edit', data={'html': '<p>novo texto</p><script>alert(1)</script>'})
        page = anon.get('/sobre').get_data(as_text=True)
        self.assertIn('novo texto', page)
        self.assertNotIn('<script>alert', page)
        self.assertNotIn('editar página', page)

        admin.post('/sobre/edit', data={'html': ''})
        self.assertIn('O que é isso?', anon.get('/sobre').get_data(as_text=True))

    def test_pinned_posts_come_first(self):
        with app.app_context():
            admin_id = User.query.filter_by(username='admin_teste').first().id
            old = Post(title='Fixado antigo', body_html='<p>a</p>', author_id=admin_id,
                       created_at=datetime(2001, 1, 1))
            new = Post(title='Recente solto', body_html='<p>b</p>', author_id=admin_id,
                       created_at=datetime(2030, 1, 1))
            db.session.add_all([old, new])
            db.session.commit()
            old_id = old.id
        admin = app.test_client()
        self.login(admin, 'admin_teste')
        res = admin.patch(f'/api/admin/posts/{old_id}', json={'pinned': True})
        self.assertTrue(res.get_json()['pinned'])
        titles = [p['title'] for p in app.test_client().get('/api/posts').get_json()]
        self.assertEqual(titles[0], 'Fixado antigo')
        admin.patch(f'/api/admin/posts/{old_id}', json={'pinned': False})
        titles = [p['title'] for p in app.test_client().get('/api/posts').get_json()]
        self.assertEqual(titles[0], 'Recente solto')


if __name__ == '__main__':
    unittest.main()
