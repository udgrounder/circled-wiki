# Tech stack
- Python >=3.9, setuptools build backend, src-layout package `circled_wiki`.
- Only Runtime dependency: PyYAML >=6.0.
- Dev dependency: pytest >=8.0.
- Console scripts: `circled-wiki` -> `circled_wiki.cli.__main__:main`; `circled-wiki-product` -> `circled_wiki.product_cli:run_product_cli`.
- No Makefile automation; repository commonly runs directly with `PYTHONPATH=src`.