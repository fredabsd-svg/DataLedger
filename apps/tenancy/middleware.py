class EscritorioAtivoMiddleware:
    """Resolve o escritório ativo da sessão e o expõe em request.escritorio.

    Isolamento: request.escritorio só pode ser um Escritorio ao qual o
    usuário autenticado tem vínculo ativo. O ID salvo na sessão é sempre
    revalidado contra os vínculos do usuário a cada requisição — nunca é
    aceito por si só, para impedir que uma sessão manipulada acesse dados
    de outro escritório.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.escritorio = None
        request.papel = None

        if request.user.is_authenticated:
            vinculos = list(request.user.vinculos.filter(ativo=True).select_related("escritorio"))
            escritorio_id = request.session.get("escritorio_id")
            vinculo = next((v for v in vinculos if v.escritorio_id == escritorio_id), None)

            # Seleção automática quando o usuário tem um único escritório,
            # poupando a etapa manual do seletor previsto no escopo.
            if vinculo is None and len(vinculos) == 1:
                vinculo = vinculos[0]
                request.session["escritorio_id"] = vinculo.escritorio_id

            if vinculo is not None:
                request.escritorio = vinculo.escritorio
                request.papel = vinculo.papel

        return self.get_response(request)
