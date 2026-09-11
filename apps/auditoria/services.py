from apps.auditoria.models import RegistroAuditoria


def registrar(*, acao, usuario=None, escritorio=None, objeto=None, detalhes=None, request=None):
    """Cria um registro de auditoria.

    Se `request` for informado, usuário/escritório/IP são inferidos dele
    quando não passados explicitamente. `detalhes` deve conter só dados não
    sensíveis (ver docstring de RegistroAuditoria).
    """
    endereco_ip = None
    if request is not None:
        endereco_ip = request.META.get("REMOTE_ADDR")
        if usuario is None and request.user.is_authenticated:
            usuario = request.user
        if escritorio is None:
            escritorio = getattr(request, "escritorio", None)

    return RegistroAuditoria.objects.create(
        usuario=usuario,
        escritorio=escritorio,
        acao=acao,
        objeto_tipo=type(objeto).__name__ if objeto is not None else "",
        objeto_id=str(getattr(objeto, "pk", "")) if objeto is not None else "",
        detalhes=detalhes or {},
        endereco_ip=endereco_ip,
    )
