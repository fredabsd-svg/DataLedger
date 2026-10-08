"""Núcleo de intercâmbio contábil do DataLedger (DL-077, fatia 1).

Um núcleo comum, e cada formato só lê e escreve:

- `canonico.py`: registros neutros (contrato entre formatos e núcleo).
- `formatos/`: leitores (arquivo -> registros + ocorrências) e escritores
  (registros -> arquivo). Registro de formatos em `formatos/__init__.py`.
- `leitura.py`: entrada comum (limites de tamanho e linhas, SHA-256, nome).
- `plano.py`: conferência (prévia, sem gravar), aplicação atômica e exportação
  do plano de contas.
"""
