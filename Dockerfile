FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

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
RUN DJANGO_SECRET_KEY=descartavel-apenas-para-collectstatic \
    python manage.py collectstatic --noinput

RUN useradd --create-home dataledger
USER dataledger

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
