FROM python:3.14-slim

# DL-068 (BL-82): a imagem é produção até dizer o contrário. Com este valor,
# settings.py recusa subir se DEBUG=True. Para rodar a imagem em
# desenvolvimento (compose local), o `.env` precisa declarar
# DJANGO_AMBIENTE=desenvolvimento — o .env.example já traz isso.
# collectstatic, mais abaixo, roda com DEBUG no padrão (False) e não é afetado.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_AMBIENTE=producao

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

# STORAGES usa CompressedManifestStaticFilesStorage (WhiteNoise), que exige o
# manifesto gerado por collectstatic. Sem esta etapa, com DEBUG=False,
# /static/* devolvia 404 e o admin do Django quebrava com "Missing
# staticfiles manifest entry" — a imagem subia e só falhava em uso real.
# staticfiles/ está no .gitignore, então NÃO vem pelo COPY: tem de ser gerada
# aqui. Roda antes do USER para que o processo tenha permissão de escrita.
#
# A chave abaixo é descartável e existe só porque settings.py exige
# DJANGO_SECRET_KEY para importar. collectstatic não assina nada, e o valor
# não é persistido como ENV na imagem — a chave real vem do ambiente em
# tempo de execução.
#
# DATABASE_URL descartável (DL-068): com DEBUG=False, settings.py exige
# DATABASE_URL para importar. Até aqui ela só existia porque o `COPY . .`
# levava o `.env` real para dentro da imagem; o `.dockerignore` passou a
# excluí-lo, então o build precisa declarar uma. O host é de um domínio
# reservado (.invalid, RFC 2606) e nada se conecta a ele: collectstatic só
# copia arquivos. A URL real vem do ambiente em tempo de execução.
RUN DJANGO_SECRET_KEY=descartavel-apenas-para-collectstatic \
    DATABASE_URL=postgres://descartavel:descartavel@banco-descartavel.invalid:5432/descartavel \
    python manage.py collectstatic --noinput

RUN useradd --create-home dataledger
USER dataledger

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
