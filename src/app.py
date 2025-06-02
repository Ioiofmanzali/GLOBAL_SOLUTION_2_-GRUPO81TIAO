import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import numpy as np
import joblib
import plotly.graph_objects as go
from datetime import datetime
from utils import buscar_nivel_rio, buscar_volume_chuva, salvar_leitura, enviar_alerta_sms, risco_enchente
import os


def on_volume_change():
    salvar_leitura('CHUVA', st.session_state.volume_chuva_hoje)


def on_nivel_change():
    salvar_leitura('RIO', st.session_state.nivel_rio_hoje)


# --- Configurações e Constantes
PATH = os.path.dirname(os.path.abspath(__file__))
PATH_MODELO_ESPERADO = PATH + "/modelos/modelo_nivel_esperado.joblib"
PATH_MODELO_PREVISAO_CHUVA = PATH + "/modelos/modelo_previsao_chuva.joblib"
CIDADE_ALVO = "São Paulo"
data_atual = datetime.now()

# --- MODIFICAÇÃO AQUI: DEFINIR O NOVO VALOR MÍNIMO
# Definindo um valor mínimo global para os inputs.
# Agora, o nível do rio terá um mínimo de 715.0.
# O volume de chuva ainda pode ser 0.0.
MIN_CHUVA_INPUT_VALUE = 0.0
MIN_RIO_INPUT_VALUE = 715.0  # 

try:
    volume_chuva_raw = float(buscar_volume_chuva()['items'][0]['valor'])
    # Garante que o volume de chuva não seja menor que o mínimo permitido pelo input
    volume_chuva = max(volume_chuva_raw, MIN_CHUVA_INPUT_VALUE)
except Exception as e:
    st.error(
        f"Erro ao buscar volume de chuva: {e}. Usando {MIN_CHUVA_INPUT_VALUE} como padrão.")
    volume_chuva = MIN_CHUVA_INPUT_VALUE  # Fallback para 0.0 se houver erro

try:
    nivel_rio_raw = float(buscar_nivel_rio()['items'][0]['valor'])
    # Garante que o nível do rio não seja menor que o mínimo permitido pelo input
    # <--- Usando MIN_RIO_INPUT_VALUE aqui
    nivel_rio = max(nivel_rio_raw, MIN_RIO_INPUT_VALUE)
except Exception as e:
    st.error(
        f"Erro ao buscar nível do rio: {e}. Usando {MIN_RIO_INPUT_VALUE} como padrão.")
    nivel_rio = MIN_RIO_INPUT_VALUE  # 
# --- FIM DA MODIFICAÇÃO ---


# --- Layout da Aplicação
st.set_page_config(page_title=f"Monitor Enchente {CIDADE_ALVO}", layout="wide")
st.title(f"🌊 Monitoramento de Enchente - {CIDADE_ALVO}")
count = st_autorefresh(interval=30 * 1000, limit=None,
                       key="freshening_counter")

# --- Sidebar para Simulador de Dados
limite_grave = st.sidebar.number_input(
    "Nível de Água Considerado Grave (m):",
    min_value=0.0,
    value=720.0, # <--- MUDE ESTE VALOR PARA UM LIMITE REAL DE ENCHENTE PARA SEU RIO EM METROS
    step=0.5,
    help="Informe o nível de água em metros."
)
limite_moderado = st.sidebar.number_input(
    "Nível de Água Considerado Moderado (m):",
    min_value=0.0,
    value=718.0, # <--- MUDE ESTE VALOR PARA UM LIMITE REAL DE ENCHENTE PARA SEU RIO EM METROS
    step=0.5,
    help="Informe o nível de água em metros."
)

st.sidebar.header("Simulador de Sensores")
nivel_rio_hoje = st.sidebar.number_input(
    "Nível Atual do Rio (m):",
    min_value=MIN_RIO_INPUT_VALUE,  # 
    value=nivel_rio,
    step=0.5,
    help="Informe o nível do rio em metros.",
    key="nivel_rio_hoje",
    on_change=on_nivel_change
)
volume_chuva_hoje = st.sidebar.number_input(
    "Volume de Chuva Hoje (mm):",
    # <--- Usando a nova variável MIN_CHUVA_INPUT_VALUE
    min_value=MIN_CHUVA_INPUT_VALUE,
    value=volume_chuva,
    step=0.5,
    help="Informe o volume de chuva em milímetros.",
    key="volume_chuva_hoje",
    on_change=on_volume_change
)

st.sidebar.markdown("---")
st.sidebar.subheader("FIAP - Global Solution - Grupo 08")
st.sidebar.markdown("""
<div style='font-size: 1em; line-height: 0.6'>
        <p>Iolanda Helena Fabbrini Manzali de Oliveira</p>
        <p>Pedro Eduardo Soares de Sousa</p>
        <p>Murilo Carone Nasser</p>
        <p>Jônatas Gomes Alves</p>
        <p>Amanda Fragnan</p>
</div>
""", unsafe_allow_html=True)

# --- Carregar Modelos de IA


@st.cache_resource
def carregar_modelos_treinados():
    try:
        model_expected = joblib.load(PATH_MODELO_ESPERADO)
        model_rain_prediction = joblib.load(PATH_MODELO_PREVISAO_CHUVA)
        return model_expected, model_rain_prediction
    except FileNotFoundError:
        st.error(
            "Erro: Arquivos de modelo não encontrados. Execute o script de treinamento ou verifique os caminhos.")
        return None, None
    except Exception as e:
        st.error(f"Erro ao carregar modelos: {e}")
        return None, None


modelo_nivel_esperado, modelo_previsao_chuva = carregar_modelos_treinados()

# --- Prever Nível Esperado Usando o Modelo IA


def prever_nivel_esperado(modelo, current_datetime):
    if modelo is None:
        st.warning("Modelo de nível esperado não carregado. Usando valor padrão.")
        return 2.0
    try:
        hour = current_datetime.hour
        day_of_year = current_datetime.timetuple().tm_yday
        day_of_week = current_datetime.weekday()

        features_for_prediction = pd.DataFrame([[hour, day_of_year, day_of_week]],
                                               columns=['HOUR', 'DAY_OF_YEAR', 'DAY_OF_WEEK'])

        prediction = modelo.predict(features_for_prediction)
        return prediction[0]
    except Exception as e:
        st.warning(f"Erro ao prever nível esperado: {e}. Usando valor padrão.")
        return 2.0

# --- Prever Nível Com Chuva Usando o Modelo IA


def prever_nivel_com_chuva(modelo, current_level, rainfall_mm, current_datetime):
    if modelo is None:
        st.warning(
            "Modelo de previsão de chuva não carregado. Usando cálculo simplificado.")
        return current_level + rainfall_mm * 0.01
    try:
        hour = current_datetime.hour
        day_of_year = current_datetime.timetuple().tm_yday
        day_of_week = current_datetime.weekday()

        features_for_prediction = pd.DataFrame([[rainfall_mm, hour, day_of_year, day_of_week]],
                                               columns=['CHUVA_MM', 'HOUR', 'DAY_OF_YEAR', 'DAY_OF_WEEK'])

        prediction = modelo.predict(features_for_prediction)
        return prediction[0]
    except Exception as e:
        st.warning(
            f"Erro ao prever nível com chuva: {e}. Usando cálculo simplificado.")
        return current_level + (rainfall_mm * 0.01)


# --- Painel Principal ---
if nivel_rio_hoje is not None and modelo_nivel_esperado is not None and modelo_previsao_chuva is not None:
    nivel_esperado_hoje = prever_nivel_esperado(
        modelo_nivel_esperado, data_atual)
    nivel_previsto_chuva = prever_nivel_com_chuva(
        modelo_previsao_chuva, nivel_rio_hoje, volume_chuva_hoje, data_atual)

    # --- Exibir Métricas Principais ---
    st.subheader("Visão Geral dos Níveis do Rio")
    col1, col2, col3 = st.columns(3)
    col1.metric("Nível Esperado (IA)", f"{nivel_esperado_hoje:.2f} m",
                help="Nível médio esperado para esta época do ano, segundo modelo de IA.")
    col2.metric("Nível Atual do Rio", f"{nivel_rio_hoje:.2f} m",
                delta=f"{nivel_rio_hoje - nivel_esperado_hoje:.2f} m vs Esperado",
                delta_color="normal" if abs(nivel_rio_hoje - nivel_esperado_hoje) < 0.5 else ("inverse" if nivel_rio_hoje < nivel_esperado_hoje else "normal"))
    col3.metric("Nível Previsto com Chuva (IA)", f"{nivel_previsto_chuva:.2f} m",
                delta=f"{nivel_previsto_chuva - nivel_rio_hoje:.2f} m vs Atual",
                help=f"Previsão considerando o nível atual e {volume_chuva_hoje}mm de chuva.")
    x_labels = ["Esperado (Hoje)", "Atual",
                f"Previsto (+{volume_chuva_hoje}mm Chuva)"]
    y_values = [nivel_esperado_hoje, nivel_rio_hoje, nivel_previsto_chuva]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x_labels,
        y=y_values,
        marker_color=['#1f77b4', '#ff7f0e', '#d62728'],
        text=[f"{v:.2f} m" for v in y_values],
        textposition='auto'
    ))

    fig.add_hline(y=limite_moderado, line_dash="dash", line_color="orange",
                  annotation_text="Risco Moderado", annotation_position="bottom right")
    fig.add_hline(y=limite_grave, line_dash="dash", line_color="red",
                  annotation_text="Risco Grave", annotation_position="bottom right")

    fig.update_layout(
        title_text="Comparativo dos Níveis do Rio",
        yaxis_title="Nível (metros)",
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Classificação de Risco e Alerta ---
    st.subheader("Avaliação de Risco de Enchente")
    risco, cor_risco, detalhes_risco = risco_enchente(
        nivel_rio_hoje, nivel_esperado_hoje, nivel_previsto_chuva, limite_moderado, limite_grave)
    st.markdown(
        f"### Classificação Atual: <span style='color:{cor_risco}; font-weight:bold;'>{risco.upper()}</span>", unsafe_allow_html=True)
    if detalhes_risco:
        st.caption(f"Justificativa: {detalhes_risco}")

    if risco == "Grave":
        st.warning(
            f"⚠️ ATENÇÃO: RISCO DE ENCHENTE GRAVE DETECTADO PARA {CIDADE_ALVO.upper()}! ⚠️")
        sms_message = (
            f"ALERTA ENCHENTE {CIDADE_ALVO.upper()}: Risco GRAVE. "
            f"Nivel atual: {nivel_rio_hoje:.2f}m. "
            f"Previsto com {volume_chuva_hoje}mm chuva: {nivel_previsto_chuva:.2f}m. "
            f"Esperado epoca: {nivel_esperado_hoje:.2f}m. "
            f"Data: {datetime.now().strftime('%d/%m %H:%M')}."
        )
        st.text_area("Mensagem do Alerta SMS:", sms_message, height=100)

        if 'sms_ja_enviado' not in st.session_state:
            st.session_state.sms_ja_enviado = False

        estado_atual_hash = hash(
            (nivel_rio_hoje, nivel_previsto_chuva, volume_chuva_hoje))
        if 'last_state_hash' not in st.session_state or st.session_state.last_state_hash != estado_atual_hash:
            st.session_state.sms_ja_enviado = False
            st.session_state.last_state_hash = estado_atual_hash

        if not st.session_state.sms_ja_enviado:
            if st.button(f"🚨 Disparar Alarme SMS para {CIDADE_ALVO} 🚨", type="primary"):
                if enviar_alerta_sms(sms_message):
                    st.session_state.sms_ja_enviado = True
                    st.rerun()
                else:
                    st.error("Falha ao enviar SMS. Verifique os logs da API.")
        else:
            st.info(
                "Um alerta SMS para as condições atuais já foi disparado ou está marcado como enviado nesta sessão.")
            if st.button("Resetar status do SMS (permitir novo envio para mesmas condições)"):
                st.session_state.sms_ja_enviado = False
                st.rerun()

    elif risco == "Moderado":
        st.warning(
            f" Atenção: Risco de enchente MODERADO para {CIDADE_ALVO}. Monitore de perto.")
    else:
        st.success(
            f" Risco de enchente MÍNIMO para {CIDADE_ALVO} nas condições atuais.")

else:
    if nivel_rio_hoje is None:
        st.error(
            "Não foi possível obter os dados atuais do nível do rio. Verifique se a API está funcionando corretamente.")
    if modelo_nivel_esperado is None or modelo_previsao_chuva is None:
        st.error("Modelos de IA não carregados. Verifique os arquivos e logs.")
    st.info("Aguardando dados e modelos para processamento...")

