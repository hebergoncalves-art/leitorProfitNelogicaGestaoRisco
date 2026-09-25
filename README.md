# Leitor Profit

Aplicativo Windows que lê o campo monetário `Res. Dia` da janela de Automações do Profit Pro. A perda no limite ou abaixo e o ganho no limite ou acima emitem sons diferentes e abrem avisos. O limite de ganho é opcional e começa vazio. As opções de **Pausar + Zerar posições** para perda e ganho são independentes e começam desligadas; quando ligadas, acionam e confirmam o comando global do Profit, sem usar a DLL da Nelogica.

## Iniciar

Neste computador, dê dois cliques em [Iniciar-LeitorProfit.cmd](Iniciar-LeitorProfit.cmd). O inicializador usa `dist/LeitorProfitV3` quando ele existe; caso contrário, usa o ambiente Python `.venv` preparado neste projeto. Se uma versão anterior estiver aberta, encerre-a pelo ícone na bandeja antes de iniciar a nova.

Na janela do aplicativo:

1. Deixe a tela **Automações** aberta no Profit, sem minimizar a janela.
2. Escolha a janela `ProfitPro` na lista e mantenha o limite de perda `-150,00` ou altere-o. Se quiser alerta ou acionamento por ganho, preencha **Limite de ganho** com valor maior que zero, por exemplo `150,00`; vazio desliga o alerta de ganho e impede marcar seu acionamento automático.
3. Se quiser impedir leitura de outra conta, digite apenas os dígitos do número da conta no campo opcional.
4. Clique em **Iniciar monitoramento**. Depois, pode deixar Chrome ou VS Code por cima do Profit na mesma área de trabalho.
5. Clique em **Testar som perda** e **Testar som ganho** para conferir os dois sons. Fechar a janela principal a envia para a bandeja do Windows; use o ícone vermelho `P` para mostrá-la ou sair.

Cada alerta é emitido uma vez por dia durante a sessão de monitoramento, mesmo que o primeiro valor lido já esteja no respectivo limite. Ao reiniciar o aplicativo, a contagem de alertas recomeça. O ganho mostra um popup verde e uma sequência ascendente de tons. Os alertas continuam independentes do acionamento automático.

Para permitir o acionamento automático, marque **Acionar Pausar + Zerar posições no limite de perda** e/ou **Acionar Pausar + Zerar posições no limite de ganho** antes de iniciar. Se marcar ganho com o campo vazio ou inválido, o aplicativo mostra um erro e desmarca a opção; a validação é repetida ao iniciar. O Profit informa que essa ação cancela ordens e encerra posições de automação **em todas as contas**. A conta opcional acima filtra a leitura, mas não restringe o comando. Com qualquer opção ligada, a leitura usa OCR: para perda, o acionamento exige um valor anterior acima do limite e duas capturas recentes e distintas no limite ou abaixo; para ganho, exige um valor anterior abaixo do limite e duas capturas recentes e distintas no limite ou acima. Se o aplicativo iniciar já no limite, ele avisa normalmente, mas não aciona o Profit até observar um cruzamento. Perda e ganho compartilham uma única tentativa por dia, registrada em `%LOCALAPPDATA%\LeitorProfit\action-state.json`; uma falha ou dúvida não provoca repetição automática. O aplicativo não traz o Profit à frente.

O modo **Automático** tenta a acessibilidade do Windows e, se o Profit não expuser o campo, passa para captura da janela com OCR local. Na versão do Profit testada neste computador, a rota que funcionou foi **OCR**. A altura de leitura padrão (220 pixels) cobre o cabeçalho observado; ajuste esse campo se o layout da plataforma mudar.

## Instalação em outro Windows

Requer Windows 10 1903 ou posterior e Python 3.12 de 64 bits. Na pasta do projeto, execute:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\Iniciar-LeitorProfit.cmd
```

Se a pasta `dist/LeitorProfitV3` estiver presente, basta executá-la; ela contém a distribuição Windows preparada neste computador e dispensa Python instalado.

Para reconstruir o executável após editar o código:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

Distribua a pasta **inteira** `dist/LeitorProfitV3`, não apenas o arquivo `.exe`.

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
- A confirmação aceita apenas prova que o diálogo foi fechado pelo Profit; confira no próprio Profit se todas as posições foram encerradas. Se a interface mudar, a validação do botão ou do texto impedirá o acionamento e emitirá um aviso de falha.
- O acionamento dirigido foi validado com o Profit coberto por outra janela no mesmo desktop. Em outra área de trabalho virtual, a leitura e o alerta continuam, mas o clique automático fica bloqueado até a validação prática nessa condição.
