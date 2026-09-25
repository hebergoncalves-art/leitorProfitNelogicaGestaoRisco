# Visão geral do Leitor Profit

Última atualização: 2026-09-25.

## O que o produto faz

O Leitor Profit é um aplicativo Windows que acompanha o valor monetário `Res. Dia` exibido na janela de Automações do Profit Pro. Ele avisa quando o resultado atinge limites configurados e pode acionar o comando global **Pausar + Zerar posições** do Profit. Não usa a DLL da Nelogica nem envia ordens diretamente.

O usuário escolhe a janela do Profit e, opcionalmente, informa os dígitos da conta para conferir o cabeçalho da leitura. Esse filtro não restringe o comando de zeramento: o comando do Profit afeta **todas as contas**.

## Recursos disponíveis

| Recurso | Comportamento |
| --- | --- |
| Limite de perda | Alerta quando `Res. Dia` é igual ou inferior ao valor negativo configurado. O zeramento automático é opcional. |
| Limite de ganho | Valor positivo opcional; alerta quando atingido ou superado. O zeramento automático tem opção independente. |
| Drawdown | Mede o recuo desde o maior resultado positivo observado na sessão. Alerta e zeramento têm opções independentes. |
| Intervalos de suspensão | Em horários locais configurados para o dia de início, impede zeramentos por perda e drawdown. Leituras, alertas e acionamento por ganho continuam. |
| Avisos | Popups, sons, estado atual e registro de eventos na janela; a janela pode ficar na bandeja do Windows. |

Cada alerta pode disparar uma vez por dia em cada sessão de monitoramento. A ação automática exige um cruzamento observado e duas capturas OCR recentes e distintas no limite. Perda e ganho compartilham uma tentativa diária; drawdown tem uma tentativa diária separada. Uma tentativa iniciada é registrada antes do comando ao Profit, inclusive se ele falhar.

Os períodos de suspensão não são salvos. Se o resultado continuar no limite ao fim de um período, perda ou drawdown exigem duas novas capturas OCR antes da ação. O pico de drawdown e o estado dos alertas são reiniciados ao começar outro monitoramento; o pico também é reiniciado na virada do dia.

## Condições e limites

- O Profit deve estar aberto e não minimizado. A leitura usa acessibilidade do Windows quando disponível ou captura da janela com OCR local; qualquer ação automática usa OCR.
- O aplicativo só conhece resultados que conseguiu observar. O pico ocorrido enquanto ele estava fechado não é recuperado.
- O fechamento do diálogo de confirmação não comprova que todas as posições foram encerradas; é preciso conferi-las no Profit.
- Alertas e ações dependem da atualização visual, da captura e do reconhecimento. Um limite configurado não garante o valor efetivo de saída.

Para instalação, operação e diagnóstico, consulte o [README](../README.md). Para o fluxo interno e as dependências, consulte a [arquitetura](architecture.md).
