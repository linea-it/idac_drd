# Diretório contendo os certificados

Inclua neste diretório os certificados usados pelo SP para assinatura e encriptação das asserções SAML
(`mykey.pem` e `mycert.pem`, referenciados em `SAML_CONFIG` no `config/settings/base.py`).

Em produção o diretório é montado como volume no serviço django (ver `production.yml`).

Caso não possua certificados válidos, gere um certificado autoassinado através dos comandos abaixo:

```bash
# criando chave
openssl genrsa -out mykey.key 2048

# mudando permissões de leitura e escrita da chave
chmod 600 mykey.key

# criando certificado a partir da chave
openssl req -new -key mykey.key -out mycert.csr
openssl x509 -req -days 365 -in mycert.csr -signkey mykey.key -out mycert.crt

cp mykey.key mykey.pem
cp mycert.crt mycert.pem
```

Importante:

- Nunca commitar chaves/certificados (o `.gitignore` já ignora `*.pem`, `*.key`, `*.csr`, `*.crt`).
- Sempre que o certificado mudar, o metadata do SP (`https://<SITE_URL>/saml2/metadata/`) precisa ser
  reenviado/registrado junto à equipe do SATOSA/LIneA.
