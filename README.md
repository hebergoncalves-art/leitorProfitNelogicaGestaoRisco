# Leitor Profit

Aplicativo Windows que **somente lê** o campo monetário `Res. Dia` da janela de Automações do Profit Pro. Quando o valor é igual ou inferior ao limite configurado, toca um som e abre um aviso. Ele não clica no Profit, não envia ordens e não usa a DLL da Nelogica.

## Iniciar

Neste computador, dê dois cliques em [Iniciar-LeitorProfit.cmd](Iniciar-LeitorProfit.cmd). O inicializador usa o executável corrigido em `dist/LeitorProfitV2` quando ele existe; caso contrário, usa o ambiente Python `.venv` preparado neste projeto. Se uma versão anterior estiver aberta, encerre-a pelo ícone na bandeja antes de iniciar a nova.

Na janela do aplicativo:

1. Deixe a tela **Automações** aberta no Profit, sem minimizar a janela.
2. Escolha a janela `ProfitPro` na lista e mantenha o limite `-150,00` ou altere-o.
3. Se quiser impedir leitura de outra conta, digite apenas os dígitos do número da conta no campo opcional.
4. Clique em **Iniciar monitoramento**. Depois, pode deixar Chrome ou VS Code por cima do Profit na mesma área de trabalho.
5. Clique em **Testar som** para conferir o volume. Fechar a janela principal a envia para a bandeja do Windows; use o ícone vermelho `P` para mostrá-la ou sair.

O modo **Automático** tenta a acessibilidade do Windows e, se o Profit não expuser o campo, passa para captura da janela com OCR local. Na versão do Profit testada neste computador, a rota que funcionou foi **OCR**. A altura de leitura padrão (220 pixels) cobre o cabeçalho observado; ajuste esse campo se o layout da plataforma mudar.

## Instalação em outro Windows

Requer Windows 10 1903 ou posterior e Python 3.12 de 64 bits. Na pasta do projeto, execute:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\Iniciar-LeitorProfit.cmd
```

Se a pasta `dist/LeitorProfitV2` estiver presente, basta executá-la; ela contém a distribuição Windows preparada neste computador e dispensa Python instalado.

Para reconstruir o executável após editar o código:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

Distribua a pasta **inteira** `dist/LeitorProfitV2`, não apenas o arquivo `.exe`.

## Diagnóstico

Para testar uma imagem sem iniciar o monitor:

```powershell
.\.venv\Scripts\python.exe -m profit_alert --image "C:\caminho\captura.png"
```

O script `diagnose_live.py` localiza a janela aberta, tenta a acessibilidade e faz uma única leitura por OCR, sem interagir com a plataforma.

## Limitações

- O Profit deve ficar **aberto e não minimizado**. O aplicativo observa a janela escolhida; mudar de conta ou de layout pode exigir nova configuração.
- A captura do Windows envia quadros quando a imagem muda. O horário exibido é o da **última mudança capturada**, não uma garantia de atualização do mercado.
- Um alerta depende da atualização visual do Profit, do reconhecimento e do áudio do computador. Ele **não limita a perda a R$ 150,00** nem substitui controles de risco da plataforma.
- Primeiro valide o comportamento com a conta de simulação. A captura fornecida e a janela aberta neste computador foram reconhecidas com OCR; não foi possível provocar uma mudança real de resultado para medir o tempo de alerta.
