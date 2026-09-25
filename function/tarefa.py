import requests
import base64
import re
import json
from datetime import datetime
from playwright.sync_api import sync_playwright
from function.erros_navegador import TIMEOUT_ERRORS
from config import DEBUG_MODE, API_CRIAR_FATURA_DEV, API_CRIAR_FATURA_PROD, API_ATUALIZAR_FATURA_DEV , API_ATUALIZAR_FATURA_PROD, GEUS_APIKEY
from database import DatabaseManager

debug_mode = DEBUG_MODE

# Baseline do DOM de um clique que funcionou, coletada uma vez por execução
# para comparar com o diagnóstico dos cliques bloqueados.
_baseline_dom_impressa = False

# Diagnóstico (JSON + screenshot) do primeiro clique bloqueado da execução.
# Causa confirmada em 02/09/2026: o ::after da .faturas__list (degradê,
# position absolute, inset 40px 0 0) cobre a metade inferior do botão nas
# listas de 1 card. Repetir por fatura (~4/dia) só inflaria o log diário.
_diagnostico_clique_impresso = False

# Inspeção do DOM ao redor do botão "Baixar 2ª via": o que está no ponto do
# clique (pilha completa e 5 pontos do botão), a cadeia de ancestrais até a
# .faturas__list com os estilos que podem bloquear o hit-test e a geometria dos
# pseudo-elementos da lista. Só lista propriedades fora do valor padrão.
_JS_INFO_DOM = """el => {
    const PROPS = ['position', 'top', 'right', 'bottom', 'left', 'inset', 'width', 'height', 'maxHeight',
        'display', 'overflow', 'clipPath', 'opacity', 'visibility', 'pointerEvents', 'zIndex', 'isolation',
        'transform', 'content', 'backgroundImage'];
    const PADRAO = {position: 'static', top: 'auto', right: 'auto', bottom: 'auto', left: 'auto', inset: 'auto',
        maxHeight: 'none', overflow: 'visible', clipPath: 'none', opacity: '1', visibility: 'visible',
        pointerEvents: 'auto', zIndex: 'auto', isolation: 'auto', transform: 'none', backgroundImage: 'none'};
    const classe = n => (n && n.getAttribute && n.getAttribute('class')) || '';
    const box = n => {
        if (!n) return null;
        const b = n.getBoundingClientRect();
        return {x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height)};
    };
    const estilo = (n, pseudo) => {
        if (!n) return null;
        const s = getComputedStyle(n, pseudo || null);
        if (pseudo && (s.content === 'none' || s.content === 'normal')) return {content: s.content};
        const o = {};
        for (const p of PROPS) { if (s[p] !== PADRAO[p]) o[p] = s[p]; }
        return o;
    };
    const lista = el.closest('.faturas__list');
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const pontos = {centro: [cx, cy], supEsq: [r.left + 2, r.top + 2], supDir: [r.right - 2, r.top + 2],
        infEsq: [r.left + 2, r.bottom - 2], infDir: [r.right - 2, r.bottom - 2]};
    const noPonto = {};
    for (const [nome, [x, y]] of Object.entries(pontos)) {
        const t = document.elementFromPoint(x, y);
        noPonto[nome] = t ? {tag: t.tagName, classe: classe(t), dentroDoBotao: el.contains(t), ehALista: t === lista} : null;
    }
    const pilha = document.elementsFromPoint(cx, cy).slice(0, 10)
        .map(n => ({tag: n.tagName, classe: classe(n), ehOBotao: el.contains(n)}));
    const cadeia = [];
    for (let n = el; n && n !== document.body && cadeia.length < 15; n = n.parentElement) {
        cadeia.push({tag: n.tagName, classe: classe(n), box: box(n), estilo: estilo(n)});
        if (n === lista) break;
    }
    let animacoes = null;
    try {
        animacoes = {documento: document.getAnimations().length,
            lista: lista ? lista.getAnimations({subtree: true}).length : null};
    } catch (e) {}
    return {
        viewport: {w: innerWidth, h: innerHeight, scrollY: Math.round(scrollY)},
        botao: {box: box(el), disabled: el.disabled,
            visivel: el.checkVisibility ? el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) : null},
        noPontoDoClique: noPonto,
        pilhaNoCentro: pilha,
        cadeiaAteALista: cadeia,
        lista: lista ? {classe: classe(lista), box: box(lista), filhos: lista.children.length,
            before: estilo(lista, '::before'), after: estilo(lista, '::after')} : null,
        animacoes: animacoes,
        htmlDaLista: lista ? lista.outerHTML.slice(0, 3000) : null
    };
}"""


def _coletar_info_dom(download_button):
    """Executa _JS_INFO_DOM no botão de download. Retorna dict ou None se falhar."""
    try:
        return download_button.evaluate(_JS_INFO_DOM)
    except Exception as e:
        print(f"⚠️ Não foi possível coletar informações do DOM: {str(e)}")
        return None


def _descrever_interceptador(erro):
    """Extrai do call log do Playwright o elemento que interceptou o clique."""
    m = re.search(r'(<[^>\n]+>)[^\n]*intercepts pointer events', str(erro))
    return m.group(1) if m else 'elemento não identificado'


def _diagnosticar_clique_bloqueado(page, download_button, nova_uc, mes_referencia, tentativa):
    """Registra no log o que está cobrindo o botão de download.

    Chamado na primeira vez em que o Playwright reporta "intercepts pointer
    events" na execução. Imprime o JSON de _JS_INFO_DOM e salva um
    screenshot em logs/ para identificar a causa do bloqueio sem precisar
    reproduzir na mão.
    """
    import os

    info = _coletar_info_dom(download_button)
    if info is not None:
        print("🔎 Diagnóstico do clique bloqueado:")
        print(json.dumps(info, ensure_ascii=False, indent=1))

    try:
        os.makedirs("logs", exist_ok=True)
        nome = (f"clique_bloqueado_{nova_uc.replace('/', '_')}_"
                f"{mes_referencia.replace('/', '_')}_t{tentativa}.png")
        caminho = os.path.join("logs", nome)
        page.screenshot(path=caminho, full_page=True)
        print(f"📸 Screenshot salvo em {caminho}")
    except Exception as e:
        print(f"⚠️ Não foi possível salvar screenshot: {str(e)}")


def _neutralizar_interceptador(page, download_button):
    """Tenta remover o que cobre o botão para permitir um clique real.

    Cobre as causas prováveis do bloqueio: pseudo-elemento da lista por cima
    do card, pointer-events:none em algum ancestral, z-index negativo ou
    recorte por overflow. Um clique real (ao contrário do dispatch_event)
    concede "user activation", necessária caso o download use window.open.

    Returns:
        list[str]: alterações feitas no DOM, para o log.
    """
    page.add_style_tag(
        content=".faturas__list::before, .faturas__list::after { pointer-events: none !important; }"
    )
    return download_button.evaluate("""el => {
        const feitas = [];
        const lista = el.closest('.faturas__list');
        for (let n = el; n && n !== document.body; n = n.parentElement) {
            const s = getComputedStyle(n);
            const cls = (n.getAttribute('class') || '').trim();
            const nome = n.tagName + (cls ? '.' + cls.split(/\\s+/).join('.') : '');
            if (s.pointerEvents === 'none') {
                n.style.setProperty('pointer-events', 'auto', 'important');
                feitas.push(nome + ': pointer-events none -> auto');
            }
            if (parseInt(s.zIndex) < 0) {
                n.style.setProperty('z-index', '1', 'important');
                feitas.push(nome + ': z-index ' + s.zIndex + ' -> 1');
            }
            if (/hidden|clip/.test(s.overflow)) {
                n.style.setProperty('overflow', 'visible', 'important');
                feitas.push(nome + ': overflow ' + s.overflow + ' -> visible');
            }
            if (n === lista) break;
        }
        return feitas;
    }""")


def _fallback_clique_interceptado(page, download_button, nova_uc, mes_referencia, tentativa, estado, erro):
    """Fallbacks para quando o clique real em "Baixar 2ª via" foi interceptado.

    Alterna a estratégia a cada interceptação dentro da mesma fatura:
    - ímpar: dispatch_event('click') direto no botão (ignora o hit-test);
    - par: neutraliza o interceptador e repete o clique real (preserva user
      activation, caso o dispatch não tenha gerado download); se ainda assim
      for interceptado, cai no dispatch_event.

    Returns:
        str: estratégia usada.
    """
    global _diagnostico_clique_impresso

    print(f"⚠️ Clique interceptado por {_descrever_interceptador(erro)}")
    if not _diagnostico_clique_impresso:
        _diagnostico_clique_impresso = True
        _diagnosticar_clique_bloqueado(page, download_button, nova_uc, mes_referencia, tentativa)

    estado['fallbacks'] = estado.get('fallbacks', 0) + 1
    if estado['fallbacks'] % 2 == 1:
        print("↪️ Fallback: dispatch_event('click') direto no botão")
        download_button.dispatch_event('click', timeout=5000)
        return 'dispatch_event'

    alteracoes = _neutralizar_interceptador(page, download_button)
    print(f"↪️ Fallback: interceptador neutralizado ({len(alteracoes)} ajustes: {alteracoes}) + clique real")
    try:
        download_button.click(timeout=5000)
        return 'neutralizar+click'
    except TIMEOUT_ERRORS as e:
        if 'intercepts pointer events' not in str(e):
            raise
        print(f"⚠️ Ainda interceptado por {_descrever_interceptador(e)} - usando dispatch_event")
        download_button.dispatch_event('click', timeout=5000)
        return 'neutralizar+dispatch_event'


def _clicar_botao_download(page, download_button, nova_uc, mes_referencia, tentativa, estado):
    """Clica em "Baixar 2ª via" com fallback quando o clique é interceptado.

    Nas UCs com apenas 1 card de fatura a própria div .faturas__list fica por
    cima do botão e o clique "real" do Playwright nunca chega nele (erro
    "intercepts pointer events"). Até 27/08/2026 o clique em "Mostrar mais
    faturas" re-renderizava a lista e limpava esse estado; o portal removeu o
    botão em 28/08 e as UCs de 1 card passaram a falhar já na 1ª tentativa.

    Args:
        estado (dict): compartilhado entre as tentativas da mesma fatura
            (controla a alternância de fallbacks).

    Returns:
        str: estratégia usada ('click', 'dispatch_event', 'neutralizar+click'
            ou 'neutralizar+dispatch_event').
    """
    global _baseline_dom_impressa

    # Espera de renderização separada do hit-test: após um page.reload() o
    # botão pode levar mais de 10 s para aparecer.
    download_button.wait_for(state='visible', timeout=30000)
    # Com a página rolada, o ::after da lista cobre o botão e o Playwright fica
    # rolando para lá e para cá até o timeout; no topo o clique passa
    # (observado em 25/09/2026 rolando a página à mão durante a execução).
    try:
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    # Baseline só de uma fatura sem fallback anterior (o DOM ainda está intacto)
    info_pre = None
    if not _baseline_dom_impressa and not estado.get('fallbacks'):
        info_pre = _coletar_info_dom(download_button)

    # Clique de teste (não clica de verdade): detecta a interceptação em ~2 s e
    # vai direto ao fallback, em vez de 10 s de rolagem. Outro motivo de timeout
    # (botão ainda animando etc.) segue para o clique normal com prazo cheio.
    try:
        download_button.click(trial=True, timeout=2000)
    except TIMEOUT_ERRORS as e:
        if 'intercepts pointer events' in str(e):
            return _fallback_clique_interceptado(page, download_button, nova_uc, mes_referencia, tentativa, estado, e)

    try:
        download_button.click(timeout=10000)
    except TIMEOUT_ERRORS as e:
        if 'intercepts pointer events' not in str(e):
            raise
        return _fallback_clique_interceptado(page, download_button, nova_uc, mes_referencia, tentativa, estado, e)

    if info_pre is not None:
        _baseline_dom_impressa = True
        print("📐 Baseline DOM de um clique normal (comparar com cliques bloqueados): "
              + json.dumps(info_pre, ensure_ascii=False))
    return 'click'


def fazer_download_com_retry(page, download_button, nova_uc, mes_referencia, primeira_fatura=False):
    """
    Função auxiliar para fazer download da fatura com retry em caso de erro de modal
    
    Args:
        page: Instância da página do Playwright
        download_button: Elemento do botão de download
        nova_uc (str): UC no formato "10/xxxxxxx-1x"
        mes_referencia (str): Mês de referência no formato "MM/AAAA"
        primeira_fatura (bool): Parâmetro mantido para compatibilidade (não usado)
    
    Returns:
        str: Arquivo em base64 se sucesso, None se falha
    """
    from function.notificar_gestor import fatura_nao_baixada
    
    max_tentativas = 5
    tentativa_atual = 0
    download_sucesso = False
    arquivo_base64 = None
    
    estado_clique = {}  # alternância de fallbacks entre as tentativas da mesma fatura

    while tentativa_atual < max_tentativas and not download_sucesso:
        tentativa_atual += 1
        print(f"Tentativa {tentativa_atual} de {max_tentativas} para download da fatura")
        
        try:
            # Clicar no botão de download (com fallback se o clique for interceptado)
            estrategia = _clicar_botao_download(page, download_button, nova_uc, mes_referencia, tentativa_atual, estado_clique)
            
            # Aguardar o download ou modal de erro com verificação periódica
            download = None
            modal_detectado = False
            tempo_espera = 0
            max_tempo_espera = 30000  # 30 segundos
            intervalo_verificacao = 1000  # 1 segundo
            
            while tempo_espera < max_tempo_espera and not download and not modal_detectado:
                try:
                    # Tentar capturar download com timeout curto
                    with page.expect_download(timeout=intervalo_verificacao) as download_info:
                        pass
                    download = download_info.value
                    break
                except:
                    # Verificar se modal de erro apareceu
                    try:
                        modal_erro = page.locator('text="Houve um erro na sua tentativa de download"')
                        if modal_erro.is_visible():
                            modal_detectado = True
                            print("🔍 Modal de erro detectado durante o download!")
                            break
                    except:
                        pass  # Continuar verificando
                    
                    tempo_espera += intervalo_verificacao
            
            if modal_detectado:
                # Fechar modal de erro
                print("🔍 Tentando fechar modal de erro...")
                botao_ok = page.locator('button:has-text("OK")')
                
                if botao_ok.is_visible():
                    botao_ok.click()
                    print("✅ Modal fechado com sucesso")
                    page.wait_for_timeout(1000)
                else:
                    # Tentar outros seletores comuns para botão OK
                    botoes_alternativos = [
                        'button[type="button"]:has-text("OK")',
                        '.btn:has-text("OK")',
                        '[role="button"]:has-text("OK")',
                        'button:text-is("OK")'
                    ]
                    
                    for seletor in botoes_alternativos:
                        try:
                            botao_alt = page.locator(seletor)
                            if botao_alt.is_visible():
                                botao_alt.click()
                                print(f"✅ Modal fechado usando seletor alternativo: {seletor}")
                                page.wait_for_timeout(1000)
                                break
                        except:
                            continue
                    else:
                        print("⚠️ Não foi possível encontrar botão OK para fechar modal")
                
                # Continuar para próxima tentativa
                raise Exception("Modal de erro detectado durante download")
            
            if not download:
                print(f"⚠️ Download não detectado após {max_tempo_espera/1000} segundos")
                print("🔄 Fazendo refresh da página para tentar novamente...")
                page.reload()
                page.wait_for_timeout(3000)  # Aguardar página carregar
                raise Exception(f"Timeout de {max_tempo_espera/1000} segundos excedido - página recarregada")
            
            # Salvar arquivo temporariamente e converter para base64
            temp_path = f"temp_fatura_{nova_uc.replace('/', '_')}_{mes_referencia.replace('/', '_')}.pdf"
            download.save_as(temp_path)
            
            # Converter para base64
            with open(temp_path, 'rb') as file:
                arquivo_base64 = base64.b64encode(file.read()).decode('utf-8')
            
            # Remover arquivo temporário
            import os
            os.remove(temp_path)
            
            download_sucesso = True
            print(f"✅ Download realizado com sucesso na tentativa {tentativa_atual} (via {estrategia})")
            
        except Exception as download_error:
            print(f"❌ Erro no download (tentativa {tentativa_atual}): {str(download_error)}")
            
            # Se não é a última tentativa, aguardar antes da próxima
            if tentativa_atual < max_tentativas:
                print(f"⏳ Aguardando antes da próxima tentativa...")
                page.wait_for_timeout(3000)
    
    # Verificar se o download foi bem-sucedido
    if not download_sucesso or arquivo_base64 is None:
        print(f"❌ Falha no download após {max_tentativas} tentativas")
        print("📞 Chamando função de notificação do gestor...")
        fatura_nao_baixada()
        return None
    
    return arquivo_base64

def processar_faturas_do_json(json_data, page, force=False, reprocessar_tudo=False):
    """
    Processa as faturas do JSON e chama as funções apropriadas
    
    Args:
        json_data (dict): Dados do JSON com as faturas organizadas
        page: Instância da página do Playwright
        force (bool): Se True, reprocessa faturas com erro
        reprocessar_tudo (bool): Se True, ignora a janela diária e reprocessa qualquer
            fatura, inclusive as que já deram sucesso hoje
    """
    import io
    import sys
    
    try:
        geradora = json_data.get("geradora")
        lista_ucs = json_data.get("lista_ucs", {})
        
        print(f"Processando geradora: {geradora}")
        print(f"Total de UCs: {len(lista_ucs)}")
        
        db = DatabaseManager()
        resultados = []
        primeira_fatura_processada = False
        
        for nova_uc, faturas in lista_ucs.items():
            print(f"\n--- Processando UC: {nova_uc} ---")
            
            # Estatísticas da UC
            uc_inicio = datetime.now()
            total_faturas_uc = len(faturas)
            faturas_sucesso_uc = 0
            faturas_erro_uc = 0
            faturas_puladas_uc = 0
            
            for fatura in faturas:
                fatura_id = fatura.get("id")
                mes_referencia = fatura.get("data_referencia")
                tarefa = fatura.get("tarefa")
                
                # Capturar log da execução desta fatura
                log_buffer = io.StringIO()
                old_stdout = sys.stdout
                
                # Criar um escritor que duplica para console e buffer
                class DualWriter:
                    def __init__(self, *writers):
                        self.writers = writers
                    def write(self, text):
                        for writer in self.writers:
                            writer.write(text)
                    def flush(self):
                        for writer in self.writers:
                            writer.flush()
                
                sys.stdout = DualWriter(old_stdout, log_buffer)
                
                print(f"Processando fatura ID: {fatura_id}, Mês: {mes_referencia}, Tarefa: {tarefa}")
                
                # Verificar status no banco de dados
                status_db, deve_processar = db.verificar_status_fatura(
                    fatura_id, force=force, reprocessar_tudo=reprocessar_tudo
                )
                
                if not deve_processar:
                    if status_db == 'sucesso':
                        print(f"   ⏭️ Fatura ID {fatura_id} já processada com SUCESSO - pulando")
                    elif status_db == 'erro':
                        print(f"   ⏭️ Fatura ID {fatura_id} com ERRO anterior - pulando (use --force para reprocessar)")
                    
                    # Restaurar stdout
                    sys.stdout = old_stdout
                    
                    faturas_puladas_uc += 1
                    resultados.append({
                        "id": fatura_id,
                        "uc": nova_uc,
                        "mes": mes_referencia,
                        "tarefa": tarefa,
                        "sucesso": False,
                        "pulada": True,
                        "motivo": status_db
                    })
                    continue
                
                # Determinar se é a primeira fatura da geradora
                eh_primeira_fatura = not primeira_fatura_processada
                
                # Variável para armazenar resultado
                resultado = False
                tipo_operacao = None
                dados_fatura = {}
                
                try:
                    if tarefa == "fatura_pendente":
                        resultado, tipo_operacao, dados_fatura = executar_fatura_pendente(nova_uc, mes_referencia, page, fatura_id, eh_primeira_fatura)
                        
                    elif tarefa == "fatura_vencida":
                        resultado, tipo_operacao, dados_fatura = executar_fatura_vencida(nova_uc, mes_referencia, page, fatura_id, fatura, eh_primeira_fatura)
                        
                    elif tarefa == "fatura_a_vencer":
                        # Usar a função de fatura vencida para faturas a vencer (com verificação de mudanças)
                        resultado, tipo_operacao, dados_fatura = executar_fatura_vencida(nova_uc, mes_referencia, page, fatura_id, fatura, eh_primeira_fatura)
                    
                    elif tarefa == "fatura_agendado":
                        # Processar fatura agendada - verificar se foi paga
                        resultado, tipo_operacao, dados_fatura = executar_fatura_agendada(nova_uc, mes_referencia, page, fatura_id, fatura, eh_primeira_fatura)
                    
                    else:
                        print(f"⚠️ Tarefa desconhecida: {tarefa}")
                        resultado = False
                        tipo_operacao = "erro"
                    
                    # Capturar log antes de restaurar stdout
                    log_execucao = log_buffer.getvalue()
                    
                    # Restaurar stdout
                    sys.stdout = old_stdout
                    
                    # Atualizar status no banco de dados com todos os dados
                    if resultado:
                        db.atualizar_status_fatura(
                            fatura_id=fatura_id,
                            status='sucesso',
                            valor=dados_fatura.get('valor'),
                            data_vencimento=dados_fatura.get('data_vencimento'),
                            situacao_pagamento=dados_fatura.get('situacao_pagamento'),
                            tipo_operacao=tipo_operacao,
                            log_execucao=log_execucao
                        )
                        faturas_sucesso_uc += 1
                    else:
                        db.atualizar_status_fatura(
                            fatura_id=fatura_id,
                            status='erro',
                            mensagem_erro=f"Falha ao processar {tarefa}",
                            tipo_operacao=tipo_operacao or "erro",
                            log_execucao=log_execucao
                        )
                        faturas_erro_uc += 1
                    
                    resultados.append({
                        "id": fatura_id,
                        "uc": nova_uc,
                        "mes": mes_referencia,
                        "tarefa": tarefa,
                        "sucesso": resultado,
                        "pulada": False
                    })
                    
                except Exception as e_fatura:
                    print(f"❌ Exceção ao processar fatura ID {fatura_id}: {str(e_fatura)}")
                    
                    # Capturar log antes de restaurar stdout
                    log_execucao = log_buffer.getvalue()
                    
                    # Restaurar stdout
                    sys.stdout = old_stdout
                    
                    db.atualizar_status_fatura(
                        fatura_id=fatura_id,
                        status='erro',
                        mensagem_erro=str(e_fatura),
                        tipo_operacao="erro",
                        log_execucao=log_execucao
                    )
                    faturas_erro_uc += 1
                    
                    resultados.append({
                        "id": fatura_id,
                        "uc": nova_uc,
                        "mes": mes_referencia,
                        "tarefa": tarefa,
                        "sucesso": False,
                        "pulada": False,
                        "erro": str(e_fatura)
                    })
                
                # Marcar que já processamos a primeira fatura (independente do sucesso)
                if not primeira_fatura_processada:
                    primeira_fatura_processada = True
            
            # Registrar execução da UC no banco
            db.registrar_execucao_uc(
                cnpj_geradora=geradora,
                nova_uc=nova_uc,
                total_faturas=total_faturas_uc,
                faturas_sucesso=faturas_sucesso_uc,
                faturas_erro=faturas_erro_uc,
                faturas_puladas=faturas_puladas_uc,
                data_hora_inicio=uc_inicio
            )
        
        # Resumo dos resultados
        sucessos = sum(1 for r in resultados if r.get("sucesso"))
        puladas = sum(1 for r in resultados if r.get("pulada"))
        total = len(resultados)
        print(f"\n📊 Resumo do processamento:")
        print(f"Total de faturas: {total}")
        print(f"Processadas com sucesso: {sucessos}")
        print(f"Puladas: {puladas}")
        print(f"Falhas: {total - sucessos - puladas}")
        
        return resultados
        
    except Exception as e:
        print(f"❌ Erro durante processamento do JSON: {str(e)}")
        return []

def executar_fatura_pendente(nova_uc, mes_referencia, page, fatura_id, primeira_fatura=False):
    """
    Executa o processamento de fatura pendente
    
    Args:
        nova_uc (str): UC no formato "10/xxxxxxx-1x"
        mes_referencia (str): Mês de referência no formato "MM/AAAA"
        page: Instância da página do Playwright
        fatura_id (int): ID da fatura do JSON
        primeira_fatura (bool): Se é a primeira fatura da geradora
    
    Returns:
        tuple: (sucesso, tipo_operacao, dados_fatura)
    """
    try:
        print(f"Iniciando processamento de fatura pendente para UC: {nova_uc}, Mês: {mes_referencia}")
        
        # 1. Buscar o mês de referência da nova_uc processada no formato MM/AAAA
        mes_busca = mes_referencia
        print(f"Buscando fatura para o mês: {mes_busca}")
        
        # 2. Listar todos os cards da página usando o seletor preciso "card-billing__date"
        cards_date = page.locator('.card-billing__date')
        cards_count = cards_date.count()
        print(f"Encontrados {cards_count} cards de fatura na página")
        
        fatura_encontrada = False
        dados_fatura = {}
        
        # 3. Verificar se existe o card referente ao mês buscado
        for i in range(cards_count):
            card_date = cards_date.nth(i)
            
            # Extrair mês e ano do card
            mes_element = card_date.locator('p').first
            ano_element = card_date.locator('p').last
            
            mes_texto = mes_element.text_content().strip()
            ano_texto = ano_element.text_content().strip()
            
            # Converter mês para número
            meses = {
                'Janeiro': '01', 'Fevereiro': '02', 'Março': '03', 'Abril': '04',
                'Maio': '05', 'Junho': '06', 'Julho': '07', 'Agosto': '08',
                'Setembro': '09', 'Outubro': '10', 'Novembro': '11', 'Dezembro': '12'
            }
            
            mes_numero = meses.get(mes_texto, '00')
            mes_card = f"{mes_numero}/{ano_texto}"
            
            print(f"Card {i+1}: {mes_texto} {ano_texto} ({mes_card})")
            
            # Verificar se é o mês que estamos buscando
            if mes_card == mes_busca:
                print(f"✓ Fatura encontrada para {mes_texto} {ano_texto}")
                fatura_encontrada = True
                
                # Buscar o card completo que contém todas as informações
                # Navegar para o elemento pai que contém todo o card da fatura
                card_completo = card_date.locator('xpath=ancestor::*[contains(@class, "card-billing") or contains(@class, "card")]').first
                
                # Verificar situação de pagamento baseada na classe CSS do card-billing__top
                situacao_element = card_completo.locator('.card-billing__top')
                situacao_class = situacao_element.get_attribute('class')
                
                # Determinar situação de pagamento
                if 'card-billing__top--green' in situacao_class:
                    situacao_pagamento = "paga"
                elif 'card-billing__top--orange' in situacao_class:
                    situacao_pagamento = "a_vencer"
                elif 'card-billing__top--red' in situacao_class:
                    situacao_pagamento = "vencida"
                else:
                    situacao_pagamento = "desconhecida"
                
                print(f"Situação de pagamento detectada: {situacao_pagamento}")
                
                # Extrair valor da fatura (seletor flexível para diferentes tamanhos)
                valor_element = card_completo.locator('.card-billing__price div[class*="min-w-"]').first
                valor_texto = valor_element.text_content().strip()
                valor = valor_texto.replace('R$', '').replace(' ', '').replace(',', '.')
                
                # Extrair data de vencimento
                vencimento_element = card_completo.locator('.font-bold').last
                vencimento_texto = vencimento_element.text_content().strip()
                
                # Converter data de vencimento para formato AAAA-MM-DD
                dia, mes, ano = vencimento_texto.split('/')
                data_vencimento = f"{ano}-{mes}-{dia}"
                
                print(f"Valor: R$ {valor}")
                print(f"Vencimento: {vencimento_texto} -> {data_vencimento}")
                
                # Fazer download da fatura com retry
                download_button = card_completo.locator('button[data-pix="false"]')
                arquivo_base64 = fazer_download_com_retry(page, download_button, nova_uc, mes_referencia, primeira_fatura)
                
                if arquivo_base64 is None:
                    print("❌ Falha no download da fatura após todas as tentativas")
                    return False, "erro", {}
                
                dados_fatura = {
                    "valor": valor,
                    "data_vencimento": data_vencimento,
                    "data_referencia": mes_referencia,
                    "arquivo_fatura": arquivo_base64,
                    "nome_arquivo_fatura": f"fatura_{nova_uc}_{mes_referencia}.pdf",
                    "situacao_pagamento": situacao_pagamento
                }
                
                break
        
        if not fatura_encontrada:
            print(f"ℹ️ Fatura não localizada para o mês {mes_busca} - situação normal")
            return True, "nao_encontrada", {}  # Retorna True pois não é um erro, apenas não foi encontrada
        
        # 4. Enviar requisição para a API
        if debug_mode:
            url = API_CRIAR_FATURA_DEV
        else:
            url = API_CRIAR_FATURA_PROD
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GEUS_APIKEY}"
        }
        
        body = {
            "id": fatura_id,
            "nova_uc": nova_uc,
            "data_vencimento": dados_fatura["data_vencimento"],
            "data_referencia": dados_fatura["data_referencia"],
            "valor": dados_fatura["valor"],
            "arquivo_fatura": dados_fatura["arquivo_fatura"],
            "nome_arquivo_fatura": dados_fatura["nome_arquivo_fatura"],
            "data_encontrada": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "situacao_pagamento": dados_fatura["situacao_pagamento"],
            "situacao_energia_a": "sem_injecao",
            "tipo_tensao": None,
            "tipo_gd": None
        }
        
        print(f"Enviando dados para API: {url}")
        response = requests.post(url, headers=headers, json=body)
        
        if response.status_code == 200:
            print("✅ Fatura enviada com sucesso para a API")
            return True, "criada", dados_fatura
        else:
            print(f"❌ Erro ao enviar fatura para API: {response.status_code}")
            print(f"Resposta: {response.text}")
            return False, "erro", dados_fatura
            
    except Exception as e:
        print(f"❌ Erro durante processamento da fatura pendente: {str(e)}")
        return False, "erro", {}


def executar_fatura_vencida(nova_uc, mes_referencia, page, fatura_id, fatura_existente=None, primeira_fatura=False):
    """
    Executa o processamento de fatura vencida
    
    Args:
        nova_uc (str): UC no formato "10/xxxxxxx-1x"
        mes_referencia (str): Mês de referência no formato "MM/AAAA"
        page: Instância da página do Playwright
        fatura_id (int): ID da fatura do JSON
        fatura_existente (dict): Dados da fatura existente para comparação (opcional)
        primeira_fatura (bool): Se é a primeira fatura da geradora
    """
    try:
        print(f"Iniciando processamento de fatura vencida para UC: {nova_uc}, Mês: {mes_referencia}")
        
        # 1. Buscar o mês de referência da nova_uc processada no formato MM/AAAA
        mes_busca = mes_referencia
        print(f"Buscando fatura para o mês: {mes_busca}")
        
        # 2. Listar todos os cards da página usando o seletor preciso "card-billing__date"
        cards_date = page.locator('.card-billing__date')
        cards_count = cards_date.count()
        print(f"Encontrados {cards_count} cards de fatura na página")
        
        fatura_encontrada = False
        dados_fatura = {}
        
        # 3. Verificar se existe o card referente ao mês buscado
        for i in range(cards_count):
            card_date = cards_date.nth(i)
            
            # Extrair mês e ano do card
            mes_element = card_date.locator('p').first
            ano_element = card_date.locator('p').last
            
            mes_texto = mes_element.text_content().strip()
            ano_texto = ano_element.text_content().strip()
            
            # Converter mês para número
            meses = {
                'Janeiro': '01', 'Fevereiro': '02', 'Março': '03', 'Abril': '04',
                'Maio': '05', 'Junho': '06', 'Julho': '07', 'Agosto': '08',
                'Setembro': '09', 'Outubro': '10', 'Novembro': '11', 'Dezembro': '12'
            }
            
            mes_numero = meses.get(mes_texto, '00')
            mes_card = f"{mes_numero}/{ano_texto}"
            
            print(f"Card {i+1}: {mes_texto} {ano_texto} ({mes_card})")
            
            # Verificar se é o mês que estamos buscando
            if mes_card == mes_busca:
                print(f"✓ Fatura encontrada para {mes_texto} {ano_texto}")
                fatura_encontrada = True
                
                # Buscar o card completo que contém todas as informações
                # Navegar para o elemento pai que contém todo o card da fatura
                card_completo = card_date.locator('xpath=ancestor::*[contains(@class, "card-billing") or contains(@class, "card")]').first
                
                # Verificar situação de pagamento baseada na classe CSS do card-billing__top
                situacao_element = card_completo.locator('.card-billing__top')
                situacao_class = situacao_element.get_attribute('class')
                
                # Determinar situação de pagamento
                if 'card-billing__top--green' in situacao_class:
                    situacao_pagamento = "paga"
                elif 'card-billing__top--orange' in situacao_class:
                    situacao_pagamento = "a_vencer"
                elif 'card-billing__top--red' in situacao_class:
                    situacao_pagamento = "vencida"
                else:
                    situacao_pagamento = "desconhecida"
                
                print(f"Situação de pagamento detectada: {situacao_pagamento}")
                
                # Extrair valor da fatura (seletor flexível para diferentes tamanhos)
                valor_element = card_completo.locator('.card-billing__price div[class*="min-w-"]').first
                valor_texto = valor_element.text_content().strip()
                valor = valor_texto.replace('R$', '').replace(' ', '').replace(',', '.')

                if valor == "0":
                    valor = "0.00"
                
                # Extrair data de vencimento
                vencimento_element = card_completo.locator('.font-bold').last
                vencimento_texto = vencimento_element.text_content().strip()
                
                # Converter data de vencimento para formato AAAA-MM-DD
                dia, mes, ano = vencimento_texto.split('/')
                data_vencimento = f"{ano}-{mes}-{dia}"
                
                print(f"Valor: R$ {valor}")
                print(f"Vencimento: {vencimento_texto} -> {data_vencimento}")
                
                # Armazenar referência do botão de download para uso posterior
                download_button = card_completo.locator('button[data-pix="false"]')
                
                # Inicializar dados básicos da fatura (sem arquivo ainda)
                dados_fatura = {
                    "valor": valor,
                    "data_vencimento": data_vencimento,
                    "data_referencia": mes_referencia,
                    "arquivo_fatura": None,
                    "nome_arquivo_fatura": f"fatura_{nova_uc}_{mes_referencia}.pdf",
                    "situacao_pagamento": situacao_pagamento
                }
                
                break
        
        if not fatura_encontrada:
            print(f"ℹ️ Fatura não localizada para o mês {mes_busca} - situação normal")
            return True, "nao_encontrada", {}  # Retorna True pois não é um erro, apenas não foi encontrada
        
        # 4. Verificar se houve mudanças além da situação de pagamento
        apenas_situacao_mudou = False
        precisa_download = True  # Por padrão, assume que precisa fazer download
        tipo_operacao = "atualizada"  # Padrão para fatura vencida
        
        if fatura_existente:
            # Comparar dados atuais com os existentes
            valor_mudou = dados_fatura["valor"] != fatura_existente.get("valor")
            vencimento_mudou = dados_fatura["data_vencimento"] != fatura_existente.get("data_vencimento")
            situacao_mudou = dados_fatura["situacao_pagamento"] != fatura_existente.get("situacao_pagamento")
            
            print(f"Comparação com fatura existente:")
            print(f"  Valor mudou: {valor_mudou} ({dados_fatura['valor']} vs {fatura_existente.get('valor')})")
            print(f"  Vencimento mudou: {vencimento_mudou} ({dados_fatura['data_vencimento']} vs {fatura_existente.get('data_vencimento')})")
            print(f"  Situação mudou: {situacao_mudou} ({dados_fatura['situacao_pagamento']} vs {fatura_existente.get('situacao_pagamento')})")
            
            # Se apenas a situação mudou (valor e vencimento não mudaram)
            if situacao_mudou and not valor_mudou and not vencimento_mudou:
                apenas_situacao_mudou = True
                precisa_download = False  # Não precisa fazer download se só a situação mudou
                tipo_operacao = "situacao_alterada"
                print("📋 Detectado: Apenas situação de pagamento foi alterada - download não necessário")
            elif situacao_mudou or valor_mudou or vencimento_mudou:
                tipo_operacao = "atualizada"
                print("📋 Detectado: Múltiplos campos foram alterados - download necessário")
            else:
                print("📋 Nenhuma alteração detectada")
                return True, "sem_alteracao", dados_fatura  # Não há necessidade de atualizar
        else:
            # Primeira vez processando esta fatura
            tipo_operacao = "criada"
        
        # 5. Fazer download apenas se necessário
        if precisa_download:
            print("📥 Iniciando download da fatura...")
            arquivo_base64 = fazer_download_com_retry(page, download_button, nova_uc, mes_referencia, primeira_fatura)
            
            if arquivo_base64 is None:
                print("❌ Falha no download da fatura após todas as tentativas")
                return False, "erro", dados_fatura
            
            # Atualizar dados da fatura com o arquivo
            dados_fatura["arquivo_fatura"] = arquivo_base64
            print("✅ Download concluído com sucesso")
        else:
            print("⏭️ Download pulado - apenas situação de pagamento mudou")
        
        # 5. Enviar requisição baseada no tipo de mudança
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GEUS_APIKEY}"
        }
        
        if apenas_situacao_mudou:
            # Cenário 1: Apenas situação de pagamento mudou - usar API de atualização
            if debug_mode:
                url = API_ATUALIZAR_FATURA_DEV
            else:
                url = API_ATUALIZAR_FATURA_PROD
            
            body = {
                "id": fatura_id,
                "situacao_pagamento": dados_fatura["situacao_pagamento"]
            }
            
            print(f"Enviando atualização de situação para API: {url}")
            print(f"Atualizando apenas situação para: {dados_fatura['situacao_pagamento']}")
            
        else:
            # Cenário 2: Múltiplos campos mudaram - usar API de criação completa
            if debug_mode:
                url = API_CRIAR_FATURA_DEV
            else:
                url = API_CRIAR_FATURA_PROD
            
            # Verificar se o arquivo foi baixado
            if dados_fatura["arquivo_fatura"] is None:
                print("❌ Erro: Tentativa de enviar dados completos sem arquivo da fatura")
                return False, "erro", dados_fatura
            
            body = {
                "id": fatura_id,
                "nova_uc": nova_uc,
                "data_vencimento": dados_fatura["data_vencimento"],
                "data_referencia": dados_fatura["data_referencia"],
                "valor": dados_fatura["valor"],
                "arquivo_fatura": dados_fatura["arquivo_fatura"],
                "nome_arquivo_fatura": dados_fatura["nome_arquivo_fatura"],
                "data_encontrada": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "situacao_pagamento": dados_fatura["situacao_pagamento"],
                "situacao_energia_a": "sem_injecao",
                "tipo_tensao": None,
                "tipo_gd": None
            }
            
            print(f"Enviando dados completos para API: {url}")
        
        response = requests.post(url, headers=headers, json=body)
        
        if response.status_code == 200:
            if apenas_situacao_mudou:
                print("✅ Situação de pagamento atualizada com sucesso")
            else:
                print("✅ Fatura enviada com sucesso para a API")
            return True, tipo_operacao, dados_fatura
        else:
            print(f"❌ Erro ao enviar para API: {response.status_code}")
            print(f"Resposta: {response.text}")
            return False, "erro", dados_fatura
            
    except Exception as e:
        print(f"❌ Erro durante processamento da fatura vencida: {str(e)}")
        return False, "erro", {}


def executar_fatura_agendada(nova_uc, mes_referencia, page, fatura_id, fatura_existente=None, primeira_fatura=False):
    """
    Executa o processamento de fatura agendada
    APENAS atualiza a situação de pagamento - SEM fazer download de boleto
    
    Args:
        nova_uc (str): UC no formato "10/xxxxxxx-1x"
        mes_referencia (str): Mês de referência no formato "MM/AAAA"
        page: Instância da página do Playwright
        fatura_id (int): ID da fatura do JSON
        fatura_existente (dict): Dados da fatura existente para comparação (opcional)
        primeira_fatura (bool): Se é a primeira fatura da geradora
    
    Returns:
        tuple: (sucesso, tipo_operacao, dados_fatura)
    """
    try:
        print(f"Iniciando processamento de fatura agendada para UC: {nova_uc}, Mês: {mes_referencia}")
        print("⚠️ Modo AGENDADO: Apenas verificação de situação de pagamento - SEM download de boleto")
        
        # 1. Buscar o mês de referência da nova_uc processada no formato MM/AAAA
        mes_busca = mes_referencia
        print(f"Buscando fatura para o mês: {mes_busca}")
        
        # 2. Listar todos os cards da página usando o seletor preciso "card-billing__date"
        cards_date = page.locator('.card-billing__date')
        cards_count = cards_date.count()
        print(f"Encontrados {cards_count} cards de fatura na página")
        
        fatura_encontrada = False
        situacao_pagamento = None
        dados_fatura = {}
        
        # 3. Verificar se existe o card referente ao mês buscado
        for i in range(cards_count):
            card_date = cards_date.nth(i)
            
            # Extrair mês e ano do card
            mes_element = card_date.locator('p').first
            ano_element = card_date.locator('p').last
            
            mes_texto = mes_element.text_content().strip()
            ano_texto = ano_element.text_content().strip()
            
            # Converter mês para número
            meses = {
                'Janeiro': '01', 'Fevereiro': '02', 'Março': '03', 'Abril': '04',
                'Maio': '05', 'Junho': '06', 'Julho': '07', 'Agosto': '08',
                'Setembro': '09', 'Outubro': '10', 'Novembro': '11', 'Dezembro': '12'
            }
            
            mes_numero = meses.get(mes_texto, '00')
            mes_card = f"{mes_numero}/{ano_texto}"
            
            print(f"Card {i+1}: {mes_texto} {ano_texto} ({mes_card})")
            
            # Verificar se é o mês que estamos buscando
            if mes_card == mes_busca:
                print(f"✓ Fatura encontrada para {mes_texto} {ano_texto}")
                fatura_encontrada = True
                
                # Buscar o card completo que contém todas as informações
                card_completo = card_date.locator('xpath=ancestor::*[contains(@class, "card-billing") or contains(@class, "card")]').first
                
                # Verificar situação de pagamento baseada na classe CSS do card-billing__top
                situacao_element = card_completo.locator('.card-billing__top')
                situacao_class = situacao_element.get_attribute('class')
                
                # Determinar situação de pagamento
                if 'card-billing__top--green' in situacao_class:
                    situacao_pagamento = "paga"
                elif 'card-billing__top--orange' in situacao_class:
                    situacao_pagamento = "a_vencer"
                elif 'card-billing__top--red' in situacao_class:
                    situacao_pagamento = "vencida"
                else:
                    situacao_pagamento = "desconhecida"
                
                print(f"Situação de pagamento detectada: {situacao_pagamento}")

                # Extrair data de vencimento (mesmo padrão de executar_fatura_vencida)
                data_vencimento = None
                try:
                    vencimento_element = card_completo.locator('.font-bold').last
                    vencimento_texto = vencimento_element.text_content().strip()
                    dia, mes, ano = vencimento_texto.split('/')
                    data_vencimento = f"{ano}-{mes}-{dia}"  # AAAA-MM-DD
                    print(f"Vencimento: {vencimento_texto} -> {data_vencimento}")
                except Exception as e:
                    print(f"⚠️ Não foi possível extrair a data de vencimento: {e}")

                dados_fatura = {
                    "situacao_pagamento": situacao_pagamento,
                    "data_vencimento": data_vencimento
                }

                break

        if not fatura_encontrada:
            print(f"ℹ️ Fatura não localizada para o mês {mes_busca}")
            return True, "nao_encontrada", {}  # Retorna True pois não é um erro, apenas não foi encontrada
        
        # 4. Lógica específica para fatura agendada - APENAS atualização de situação
        # Se a fatura foi paga, atualizar para "paga"
        # Se ainda está a_vencer ou vencida, manter como "agendado"
        
        if debug_mode:
            url = API_ATUALIZAR_FATURA_DEV
        else:
            url = API_ATUALIZAR_FATURA_PROD
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GEUS_APIKEY}"
        }
        
        if situacao_pagamento == "paga":
            print("💳 Fatura agendada foi PAGA - atualizando situação para 'paga'")
            
            body = {
                "id": fatura_id,
                "situacao_pagamento": "paga"
            }
            
            print(f"Enviando atualização de situação para 'paga' via API: {url}")
            response = requests.post(url, headers=headers, json=body)
            
            if response.status_code == 200:
                print("✅ Fatura atualizada para 'paga' com sucesso")
                return True, "situacao_alterada", dados_fatura
            else:
                print(f"❌ Erro ao enviar para API: {response.status_code}")
                print(f"Resposta: {response.text}")
                return False, "erro", dados_fatura
        
        elif situacao_pagamento in ["a_vencer", "vencida"]:
            # Se a fatura agendada permanecer vencida por 2 dias ou mais após o
            # vencimento, reclassificar para "vencida" (o pagamento agendado falhou).
            # Assim ela volta ao fluxo normal de fatura vencida na próxima execução.
            reclassificar = False
            if situacao_pagamento == "vencida" and data_vencimento:
                try:
                    venc = datetime.strptime(data_vencimento, "%Y-%m-%d").date()
                    dias_desde_vencimento = (datetime.now().date() - venc).days
                    if dias_desde_vencimento >= 2:
                        reclassificar = True
                        print(f"⏰ Fatura agendada vencida há {dias_desde_vencimento} dia(s) - reclassificando para 'vencida'")
                except Exception as e:
                    print(f"⚠️ Erro ao avaliar prazo de vencimento: {e}")

            if reclassificar:
                body = {
                    "id": fatura_id,
                    "situacao_pagamento": "vencida"
                }

                print(f"Enviando reclassificação para 'vencida' via API: {url}")
                response = requests.post(url, headers=headers, json=body)

                if response.status_code == 200:
                    print("✅ Fatura reclassificada para 'vencida' com sucesso")
                    dados_fatura["situacao_pagamento"] = "vencida"
                    return True, "situacao_alterada", dados_fatura
                else:
                    print(f"❌ Erro ao enviar para API: {response.status_code}")
                    print(f"Resposta: {response.text}")
                    return False, "erro", dados_fatura

            print(f"📅 Fatura ainda está como '{situacao_pagamento}' - mantendo como 'agendado'")
            print("✓ Nenhuma mudança detectada - não é necessário enviar para API")
            return True, "sem_alteracao", dados_fatura
        
        else:
            print(f"⚠️ Situação de pagamento inesperada: {situacao_pagamento}")
            return False, "erro", dados_fatura
            
    except Exception as e:
        print(f"❌ Erro durante processamento da fatura agendada: {str(e)}")
        return False, "erro", {}
