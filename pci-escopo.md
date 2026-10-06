# Palavras do escopo PCI neste laboratório

Isto não é um laudo e o serviço não está certificado. É o vocabulário para explicar o que, aqui, toca dado de cartão e o que não toca. A referência é o PCI DSS 4.0: dado de conta entra no escopo quando o sistema armazena, processa ou transmite.

## As palavras

**Dado de conta.** O conjunto. Junta o dado do portador e o dado sensível de autenticação. É ele que define o escopo, não o fato de o sistema ser "de pagamento".

**Dado do portador (CHD).** PAN, nome do portador, validade e service code. O PAN sozinho já basta para o dado existir. Nome, validade e service code, sem PAN, não puxam o sistema para dentro do escopo.

**PAN.** O número do cartão, 13 a 19 dígitos. É o dado que manda. Neste serviço ele chega no `POST /payments`, no campo `card`.

**Dado sensível de autenticação (SAD).** Trilha magnética, código de verificação (CVV, CVC, CID) e PIN ou bloco de PIN. Não pode ficar gravado depois da autorização. Este laboratório não tem campo para nenhum dos três.

**Ambiente de dados de cartão (CDE).** Onde o dado de conta é armazenado, processado ou transmitido. Quem está ligado a esse ambiente e consegue afetar a segurança dele também entra no escopo, mesmo sem ver o PAN.

**Segmentação.** Separar rede e fluxo para um sistema não herdar o escopo de outro. Sem segmentação, o conectado entra junto.

**Truncamento.** Guardar só um pedaço do PAN, em geral os últimos 4. Sozinho, não reconstitui o cartão. Os últimos 4 aparecem no Postgres, no `GET /payments/{id}` e no dashboard.

**Máscara.** O que uma pessoa vê. Log e tela não mostram o número inteiro. O redator de log troca sequências de 13 a 19 dígitos. Isso não substitui o truncamento no banco: máscara é exibição, truncamento é o que foi persistido.

**Hash com chave.** HMAC-SHA256 do PAN com o `PAN_PEPPER`. Um SHA-256 puro de PAN é fraco: o espaço de cartões cabe numa tabela. O pepper fica só no ambiente, não no git. O digest (`pan_hmac`) é o que o Redis e o Postgres usam como fingerprint.

**Tokenização.** Trocar o PAN por um valor que não é o PAN, e o original fica num cofre. Este laboratório não tokeniza. O HMAC não é um token: não dá para voltar ao PAN, e também não dá para mandar o digest a um adquirente no lugar do cartão.

**BIN.** Os primeiros dígitos, usados para achar o emissor. Não é o PAN. Aqui os 6 primeiros saem do próprio número, não do campo `bin` que o cliente manda, quando o controle está ligado.

**Em trânsito e em repouso.** Em trânsito é o PAN no corpo do `POST`. Em repouso seria o PAN gravado. Em repouso, neste código, o PAN não fica: ficam o HMAC e os últimos 4.

**SAD depois da autorização.** A regra que proíbe guardar CVV, trilha e PIN. Não se aplica a um campo que não existe. O OTP do challenge não é CVV. É um passo a mais nosso. Com `EXPOSE_OTP=true` ele volta no JSON, e isso é só da demonstração. Em produção esse campo não existe.

## O que entra no escopo daqui

| pedaço | vê o PAN em claro? | por quê |
| --- | --- | --- |
| Processo da API, no instante do `POST /payments` | sim | processa e transmite o campo `card` |
| Log da aplicação | não, se o redator pegou | a regra é não logar o corpo |
| Redis | não | guarda o HMAC, contadores, trava, replay e OTP |
| Postgres | não | guarda HMAC, últimos 4, BIN, e-mail, IPs e a decisão |
| Mock do PSP | não | recebe id, valor, moeda e a chave de idempotência |
| Dashboard e `GET /payments/{id}` | não | mostram os últimos 4 |

O mock fica fora do fluxo do PAN. Redis e Postgres ficam no escopo de suporte: não têm o número, mas guardam o que foi derivado dele e a trava que impede cobrar duas vezes. Quem comprometer o `PAN_PEPPER` junto com o digest volta a poder testar PANs contra o HMAC. O pepper é o segredo que segura essa redução.

## O que este laboratório não fecha

O `POST` é HTTP, sem TLS. Em produção o PAN em trânsito teria que ir em canal criptografado. O número existe em claro na memória do request, entre a validação e o HMAC. E-mail e IP não são CHD, mas identificam a pessoa e continuam no Postgres porque o velocity precisa deles.
