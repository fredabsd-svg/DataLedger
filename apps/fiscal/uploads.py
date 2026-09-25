"""`FileUploadHandler` próprio da recepção fiscal — achado A10 da auditoria
rodada 1.

A auditoria mediu: `apps.fiscal.services._ler_bytes_do_arquivo_enviado`
protege a MEMÓRIA (confere `.size` antes de `.chunks()`, e para de somar
assim que ultrapassa o limite — ver o docstring daquela função), mas o
parser multipart do PRÓPRIO Django já tinha escrito o corpo INTEIRO em
disco (`TemporaryUploadedFile`) antes de `receber_envio` sequer ser
chamado. Um upload de, digamos, 2 GB gravava os 2 GB em disco (e consumia
banda inteira) só para ser recusado DEPOIS — a frase "recusado antes de
ser lido inteiro" no relatório da etapa anterior valia só para memória,
não para disco nem banda. Este módulo fecha essa lacuna.

`LimiteDeTamanhoUploadHandler` é inserido na FRENTE da lista de
`request.upload_handlers` (por isso é o PRIMEIRO a ver cada pedaço) só na
view de envio (`apps.fiscal.views_web.recepcao` — ver o comentário lá
sobre a ordem com CSRF), e SÓ conta bytes — nunca decide o que fazer com
eles: ao ultrapassar o limite, levanta `django.core.files.uploadhandler.
StopUpload(connection_reset=False)`, que instrui o parser multipart do
Django a PARAR de processar o upload (sem gravar mais nada em disco) mas
continuar CONSUMINDO o restante da requisição HTTP — evita o "connection
reset" abrupto que `connection_reset=True` produziria (a página do cliente
mostraria erro de rede, não a mensagem do formulário).

Depois do `StopUpload`, `request.FILES` não tem o arquivo completo — a
view detecta isso por `handler.excedeu` (atributo próprio, não uma API do
Django) e mostra a mensagem de formulário, nunca 500.
"""

from __future__ import annotations

from django.core.files.uploadhandler import FileUploadHandler, StopUpload


class LimiteDeTamanhoUploadHandler(FileUploadHandler):
    """Aborta o upload (sem gravar mais nada em disco/memória) assim que o
    total recebido ultrapassa `limite_bytes`.

    Só CONTA bytes — nunca decide onde armazenar o arquivo: os handlers
    padrão do Django (`MemoryFileUploadHandler`/`TemporaryFileUploadHandler`,
    que continuam na lista, DEPOIS deste) continuam responsáveis por isso,
    desde que este handler não aborte antes.
    """

    def __init__(self, *args, limite_bytes: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.limite_bytes = limite_bytes
        self.total_recebido = 0
        # Nome de atributo PRÓPRIO (não é API do Django) — a view lê isto
        # depois do parse para saber se precisa mostrar a mensagem de
        # "arquivo grande demais" em vez de "nenhum arquivo enviado".
        self.excedeu = False

    def receive_data_chunk(self, raw_data, start):
        self.total_recebido += len(raw_data)
        if self.total_recebido > self.limite_bytes:
            self.excedeu = True
            # `connection_reset=False`: o Django consome o RESTO do corpo
            # da requisição sem repassar a nenhum handler (nem escreve mais
            # nada em disco/memória) — a conexão HTTP não é derrubada, e a
            # view consegue responder normalmente com uma página de erro.
            raise StopUpload(connection_reset=False)
        return raw_data

    def file_complete(self, file_size):
        # Devolve `None` de propósito: este handler nunca produz o
        # `UploadedFile` final — isso é responsabilidade dos handlers
        # padrão (memória/arquivo temporário) que continuam na lista,
        # depois deste. Este método existe só para completar o contrato
        # de `FileUploadHandler`.
        return None
