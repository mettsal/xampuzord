#!/usr/bin/env python
"""Temas: avaliação cruzada + predição com limiar de confiança.

Rótulos vêm de (1) --labels: JSON {"<id>": "<tema>"} feito à mão (ouro) e
(2) --seeds: JSON {"<tag>": "<tema>"} (ex. {"pásion": "amor"}), rótulo fraco
por pasta. Ouro vence semente. Modelo: TF-IDF (palavra + caractere) + LogReg.

  python tools/classify/themes.py --labels instance/labels.json --seeds tools/classify/seeds.json
  python tools/classify/themes.py ... --predict instance/classifications.json --threshold 0.6

Sem --predict só avalia (5-fold estratificado, macro-F1 vs. baseline, matriz de
confusão, erros mais "confiantes"). Com --predict grava, para TODO poema:
{"length": curto|longo|null, "theme": tema|null}; tema só acima do limiar.
Poema que já é rótulo ouro mantém o rótulo ouro.
"""
import argparse
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from tools.classify.text import length_class, tag_values  # noqa: E402


def load_labels(rows, labels_path, seeds_path):
    gold = {}
    if labels_path and os.path.exists(labels_path):
        gold = {int(k): v for k, v in json.load(open(labels_path, encoding='utf-8')).items()}
    seeds = json.load(open(seeds_path, encoding='utf-8')) if seeds_path else {}
    seeds = {k.lower(): v for k, v in seeds.items()}
    labels, source = {}, {}
    for r in rows:
        themes = {seeds[t] for t in tag_values(r['tags']) if t in seeds}
        if len(themes) == 1:
            labels[r['id']], source[r['id']] = themes.pop(), 'seed'
    for pid, theme in gold.items():
        labels[pid], source[pid] = theme, 'gold'
    return labels, source


def pipeline():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, make_pipeline
    feats = FeatureUnion([
        ('w', TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ('c', TfidfVectorizer(lowercase=True, analyzer='char_wb', ngram_range=(3, 5),
                              min_df=2, sublinear_tf=True)),
    ])
    return make_pipeline(feats, LogisticRegression(max_iter=2000, class_weight='balanced', C=4))


def evaluate(rows, labels, source):
    import numpy as np
    from sklearn.dummy import DummyClassifier
    from sklearn.metrics import classification_report, confusion_matrix, f1_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    by_id = {r['id']: r for r in rows}
    ids = [i for i in labels if i in by_id]
    X, y = [by_id[i]['text'] for i in ids], np.array([labels[i] for i in ids])
    counts = Counter(y)
    print('rótulos:', dict(counts), '| ouro:', sum(source[i] == 'gold' for i in ids))
    folds = min(5, min(counts.values()))
    if folds < 2:
        sys.exit('Classe com <2 exemplos: rotule mais antes de avaliar.')
    cv = StratifiedKFold(folds, shuffle=True, random_state=0)
    proba = cross_val_predict(pipeline(), X, y, cv=cv, method='predict_proba')
    classes = np.array(sorted(counts))
    pred = classes[proba.argmax(1)]
    base = cross_val_predict(DummyClassifier(strategy='most_frequent'), X, y, cv=cv)
    print(f'\nmacro-F1 modelo   : {f1_score(y, pred, average="macro"):.3f}')
    print(f'macro-F1 baseline : {f1_score(y, base, average="macro"):.3f} (classe majoritária)')
    print('\n', classification_report(y, pred, zero_division=0))
    print('matriz (linhas=real, colunas=previsto):', list(classes))
    print(confusion_matrix(y, pred, labels=classes))
    wrong = sorted((proba[k].max(), ids[k], y[k], pred[k]) for k in range(len(ids)) if pred[k] != y[k])
    print('\nerros mais confiantes (confira se o RÓTULO é que está errado):')
    for conf, pid, real, got in wrong[::-1][:15]:
        print(f'  {conf:.2f} #{pid} "{by_id[pid]["title"][:40]}" real={real} previsto={got}')
    for thr in (0.5, 0.6, 0.7, 0.8):
        keep = proba.max(1) >= thr
        acc = (pred[keep] == y[keep]).mean() if keep.any() else float('nan')
        print(f'limiar {thr}: cobertura {keep.mean():.0%}, acerto {acc:.0%}')


def predict(rows, labels, source, threshold, cutoff, out):
    import numpy as np
    by_id = {r['id']: r for r in rows}
    ids = [i for i in labels if i in by_id]
    model = pipeline().fit([by_id[i]['text'] for i in ids], [labels[i] for i in ids])
    proba = model.predict_proba([r['text'] for r in rows])
    result = {}
    for r, p in zip(rows, proba):
        theme = None
        if source.get(r['id']) == 'gold':
            theme = labels[r['id']]
        elif p.max() >= threshold:
            theme = model.classes_[int(np.argmax(p))]
        result[r['id']] = {'length': length_class(r['n_lines'], r['tags'], cutoff), 'theme': theme}
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(f'{len(result)} poemas -> {out}; com tema: {sum(v["theme"] is not None for v in result.values())}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', default=os.path.join(ROOT, 'instance', 'corpus.json'))
    ap.add_argument('--labels')
    ap.add_argument('--seeds')
    ap.add_argument('--cutoff', type=int, default=40)
    ap.add_argument('--threshold', type=float, default=0.6)
    ap.add_argument('--predict', help='grava classifications.json neste caminho')
    args = ap.parse_args()
    rows = json.load(open(args.corpus, encoding='utf-8'))
    labels, source = load_labels(rows, args.labels, args.seeds)
    if not labels:
        sys.exit('Sem rótulos: passe --labels e/ou --seeds.')
    evaluate(rows, labels, source)
    if args.predict:
        predict(rows, labels, source, args.threshold, args.cutoff, args.predict)


if __name__ == '__main__':
    main()
