# Arquitetura do Leitor Profit

Última atualização: 2026-09-25.

## Componentes

| Área | Responsabilidade |
| --- | --- |
| `profit_alert/app.py` | Interface Tkinter, configuração da sessão, janela de intervalos, sons, avisos e consumo dos eventos do monitor. |
| `profit_alert/windows.py` | Localização e validação da janela Win32 do Profit e verificação da área de trabalho virtual. |
| `profit_alert/readers.py` | Leitura por UI Automation ou captura da janela com `windows-capture` e OCR local. Produz `Reading` com valor, origem, texto e horário da captura. |
| `profit_alert/core.py` | Conversão de valores, limites de alerta, confirmação dos gatilhos de ação e cálculo do drawdown observado. |
| `profit_alert/suspension.py` | Validação, união e consulta dos intervalos de suspensão do dia local. |
| `profit_alert/monitor.py` | Thread de monitoramento, escolha do método de leitura, aplicação das regras e emissão de `MonitorEvent`. |
| `profit_alert/action.py` | Identificação do botão vermelho e confirmação dirigida do comando **Pausar + Zerar posições**. |
| `profit_alert/action_store.py` | Reserva persistente da tentativa diária de ação em arquivos JSON locais. |

## Fluxo de leitura e acionamento

1. A interface seleciona uma janela do Profit, valida os campos e cria um `MonitorConfig`. Uma fila `queue.Queue` liga a thread do monitor à thread gráfica; somente a thread gráfica atualiza o Tkinter.
2. Sem acionamento automático, o modo automático tenta UI Automation e passa para captura com OCR se o campo não ficar acessível. Com qualquer acionamento automático, usa captura OCR da janela completa para permitir a identificação do botão.
3. O leitor entrega `Reading` ao monitor. Uma conta opcional filtra leituras cujo cabeçalho não contenha os dígitos informados. Os limites de perda e ganho e o pico de drawdown geram eventos de alerta independentes das ações.
4. Para agir, `ActionGate` exige cruzamento observado e duas capturas recentes, distintas e no limite. Se vários gatilhos estiverem prontos na mesma captura, a prioridade é perda, ganho e drawdown; os demais exigem novo cruzamento.
5. Antes de acionar o Profit, o monitor reserva a tentativa diária. Perda e ganho usam `%LOCALAPPDATA%\LeitorProfit\action-state.json`; drawdown usa `drawdown-action-state.json`. A reserva permanece consumida mesmo diante de falha.
6. `ProfitAction` confere janela, processo, área de trabalho virtual, idade da captura, botão e texto do diálogo global. A confirmação é dirigida à janela selecionada, sem mover o cursor global nem trazer o Profit à frente. Fechar o diálogo não verifica o estado final das posições.

Os intervalos de suspensão são definidos para a data local em que o monitoramento começa. Durante um intervalo, o monitor continua lendo e alertando, mas descarta confirmações de ação por perda e drawdown sem reservar tentativa. Ao sair do intervalo, exige duas novas capturas. O horário é verificado novamente antes do comando e da confirmação final; uma tentativa já reservada continua consumida se o intervalo começar durante sua execução.

## Estado e dependências

As configurações da interface, os intervalos e o pico de drawdown vivem somente na sessão atual. Os dois arquivos de `ActionStore` guardam o estado persistente das tentativas diárias; não há banco de dados nem serviço remoto no fluxo de monitoramento.

O aplicativo usa Tkinter e APIs Win32/COM para interface e identificação de janelas, `uiautomation` para leitura de acessibilidade, `windows-capture` para quadros da janela, `rapidocr`/`onnxruntime` para OCR e `pystray` para a bandeja. As versões das dependências instaláveis estão fixadas em [`requirements.txt`](../requirements.txt).

`profit_alert/__main__.py` inicia a interface ou diagnostica uma imagem com `--image`; `run_app.py` é a entrada do executável e inclui modos de verificação. O [inicializador](../Iniciar-LeitorProfit.cmd) escolhe o pacote disponível antes do ambiente Python; [`build.ps1`](../build.ps1) gera `dist/LeitorProfitV3` com PyInstaller. Consulte o [README](../README.md) para os comandos de uso e instalação.
