import os
from pandas_datareader import data as fred
from config import FRED_API_KEY
import streamlit as st
import seaborn as sns  
from PyQt5 import QtCore
try:
    qt_plugin_path = os.path.join(os.path.dirname(QtCore.__file__), "Qt", "plugins")
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = qt_plugin_path
except ImportError:
    print("PyQt5 не установлен, графики могут не отображаться")
from fpdf import FPDF
from datetime import datetime
from fredapi import Fred
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
import tempfile
fred = Fred(api_key=FRED_API_KEY)
class UnicodePDF(FPDF):
    def __init__(self):
        super().__init__()
        try:
            # Добавляем обычный и жирный шрифты
            self.add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)
            self.add_font('DejaVu', 'B', 'DejaVuSans-Bold.ttf', uni=True)
            self.set_font('DejaVu', '', 12)  # Устанавливаем обычный шрифт по умолчанию
        except Exception as e:
            st.error(f"Ошибка загрузки шрифтов: {str(e)}")
            # Резервные шрифты, если DejaVu не доступен
            self.set_font('Arial', '', 12)
    
    def safe_text(self, text):
        """Функция для безопасного вывода текста"""
        try:
            return text.encode('latin1', 'replace').decode('latin1')
        except:
            return text.encode('utf-8', 'replace').decode('utf-8')

# Конфигурация Streamlit
st.set_page_config(layout="wide", page_title="Анализ нефти и CPI")
st.title("📊 Анализ взаимосвязи нефти и индекса потребительских цен (CPI)")
# Загрузка данных
@st.cache_data
def load_data():
    start_date = '1986-01-01'
    cpi = fred.get_series('CPIAUCSL', observation_start=start_date)
    oil = fred.get_series('DCOILWTICO', observation_start=start_date)
    oil_monthly = oil.resample('ME').mean()
    
    # Выравниваем индексы
    cpi.index = cpi.index.to_period('M').to_timestamp('M')
    oil_monthly.index = oil_monthly.index.to_period('M').to_timestamp('M')
    
    # Объединяем данные
    df = pd.DataFrame({'CPI': cpi, 'Oil': oil_monthly}).dropna()
    return df

df = load_data()

# Сайдбар с настройками
st.sidebar.header("Настройки анализа")
start_date = st.sidebar.date_input(
    "Начальная дата", 
    value=pd.to_datetime('1986-01-01'),
    min_value=pd.to_datetime('1980-01-01'),
    max_value=pd.to_datetime('2023-12-31')
)

max_lag = st.sidebar.slider("Максимальный лаг (месяцы)", 1, 12, 3)
confidence_level = st.sidebar.slider("Уровень доверия (%)", 90, 99, 95)

# Фильтрация данных по дате
df_filtered = df[df.index >= pd.to_datetime(start_date)]

# Расчет изменений
cpi_changes = df_filtered['CPI'].pct_change().dropna()
oil_changes = df_filtered['Oil'].pct_change().dropna()

# Основные метрики
if len(cpi_changes) >= 2 and len(oil_changes) >= 2:
    corr, p_value = stats.pearsonr(cpi_changes, oil_changes)
    r_squared = corr**2
    
    # Отображение метрик
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Корреляция (R)", f"{corr:.2f}")
    with col2:
        st.metric("R²", f"{r_squared:.2f}")
    with col3:
        st.metric("p-value", f"{p_value:.3f}")

# Функция для создания графиков
def create_plots():
    # Основные графики
    fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    df_filtered.plot(ax=ax1, title='CPI и нефть (номинальные значения)')
    df_filtered.pct_change().plot(ax=ax2, title='Месячные изменения (%)')
    ax2.axhline(0, color='grey', linestyle='--')
    for ax in [ax1, ax2]:
        ax.grid(True)
    plt.tight_layout()
    st.pyplot(fig1)
    
    # Графики с лагами
    for lag in range(0, max_lag + 1):
        df_shifted = pd.DataFrame({
            'CPI_change': df_filtered['CPI'].pct_change(),
            'Oil_lagged': df_filtered['Oil'].pct_change().shift(lag)
        }).dropna()
        
        if len(df_shifted) >= 2:
            corr_lag, p_value_lag = stats.pearsonr(df_shifted['Oil_lagged'], df_shifted['CPI_change'])
            r_squared_lag = corr_lag**2
            
            fig2 = plt.figure(figsize=(10, 6))
            sns.regplot(
                x='Oil_lagged', y='CPI_change', data=df_shifted,
                scatter_kws={'alpha': 0.3, 'color': 'blue'},
                line_kws={'color': 'red', 'lw': 2},
                ci=confidence_level,
                label=f'R²={r_squared_lag:.2f}'
            )
            
            sns.regplot(
                x='Oil_lagged', y='CPI_change', data=df_shifted,
                scatter=False,
                line_kws={'color': 'green', 'lw': 1, 'linestyle': '--'},
                ci=confidence_level,
                truncate=False
            )
            
            plt.title(f'Влияние нефти (лаг {lag} месяц) на CPI\nR = {corr_lag:.2f}, R² = {r_squared_lag:.2f}')
            plt.xlabel('Изменение нефти за предыдущий месяц (%)')
            plt.ylabel('Изменение CPI (%)')
            plt.grid(True)
            plt.legend()
            st.pyplot(fig2)
            
            with st.expander(f"Статистика для лага {lag} месяц(ев)"):
                st.write(f"Коэффициент корреляции Пирсона (R): {corr_lag:.2f}")
                st.write(f"Коэффициент детерминации (R²): {r_squared_lag:.2f}")
                st.write(f"p-value: {p_value_lag:.3f}")

# Отображение графиков
create_plots()

# Генерация PDF отчета
def create_pdf():
    try:
        pdf = UnicodePDF()
        pdf.add_page()
        
        # Заголовок
        pdf.set_font('DejaVu', 'B', 16)
        pdf.cell(0, 10, pdf.safe_text('Oil and CPI Analysis'), 0, 1, 'C')
        pdf.ln(10)
        
        # Основная информация
        pdf.set_font('DejaVu', '', 12)
        pdf.cell(0, 10, pdf.safe_text(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"), 0, 1)
        pdf.cell(0, 10, pdf.safe_text(f"Analysis period: {start_date} - {df_filtered.index[-1].strftime('%Y-%m-%d')}"), 0, 1)
        pdf.ln(15)
        
        # Основные метрики
        pdf.set_font('DejaVu', 'B', 14)
        pdf.cell(0, 10, pdf.safe_text("Key Metrics:"), 0, 1)
        pdf.set_font('DejaVu', '', 12)
        pdf.cell(0, 10, pdf.safe_text(f"Correlation (R): {corr:.2f}"), 0, 1)
        pdf.cell(0, 10, pdf.safe_text(f"R²: {r_squared:.2f}"), 0, 1)
        pdf.cell(0, 10, pdf.safe_text(f"p-value: {p_value:.3f}"), 0, 1)
        pdf.ln(15)
        
        # Сохраняем и добавляем первый график
        fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12))
        df_filtered.plot(ax=ax1, title='CPI and Oil (Nominal Values)')
        df_filtered.pct_change().plot(ax=ax2, title='Monthly Changes (%)')
        ax2.axhline(0, color='grey', linestyle='--')
        for ax in [ax1, ax2]:
            ax.grid(True)
        
        temp_plot1 = "temp_plot1.png"
        fig1.savefig(temp_plot1, bbox_inches='tight', dpi=150)
        plt.close(fig1)
        
        pdf.set_font('DejaVu', 'B', 14)
        pdf.cell(0, 10, pdf.safe_text("Analysis Charts:"), 0, 1)
        pdf.ln(5)
        pdf.image(temp_plot1, x=10, w=190)
        pdf.ln(10)
        
        # Графики с лагами
        for lag in range(0, max_lag + 1):
            df_shifted = pd.DataFrame({
                'CPI_change': df_filtered['CPI'].pct_change(),
                'Oil_lagged': df_filtered['Oil'].pct_change().shift(lag)
            }).dropna()
            
            if len(df_shifted) >= 2:
                corr_lag, p_value_lag = stats.pearsonr(df_shifted['Oil_lagged'], df_shifted['CPI_change'])
                r_squared_lag = corr_lag**2
                
                fig2 = plt.figure(figsize=(10, 8))
                sns.regplot(
                    x='Oil_lagged', y='CPI_change', data=df_shifted,
                    scatter_kws={'alpha': 0.3, 'color': 'blue'},
                    line_kws={'color': 'red', 'lw': 2},
                    ci=confidence_level,
                    label=f'R²={r_squared_lag:.2f}'
                )
                
                sns.regplot(
                    x='Oil_lagged', y='CPI_change', data=df_shifted,
                    scatter=False,
                    line_kws={'color': 'green', 'lw': 1, 'linestyle': '--'},
                    ci=confidence_level,
                    truncate=False
                )
                
                plt.title(f'Oil impact (lag {lag} month) on CPI\nR = {corr_lag:.2f}, R² = {r_squared_lag:.2f}')
                plt.xlabel('Oil price change from previous month (%)')
                plt.ylabel('CPI change (%)')
                plt.grid(True)
                plt.legend()
                
                temp_plot_lag = f"temp_plot_lag{lag}.png"
                fig2.savefig(temp_plot_lag, bbox_inches='tight', dpi=150)
                plt.close(fig2)
                
                pdf.add_page()  # Новая страница для каждого лага
                pdf.image(temp_plot_lag, x=10, w=190)
                pdf.ln(10)
                
                pdf.set_font('DejaVu', 'B', 12)
                pdf.cell(0, 10, pdf.safe_text(f"Analysis with {lag} month lag:"), 0, 1)
                pdf.set_font('DejaVu', '', 12)
                pdf.cell(0, 10, pdf.safe_text(f"Correlation coefficient (R): {corr_lag:.2f}"), 0, 1)
                pdf.cell(0, 10, pdf.safe_text(f"R²: {r_squared_lag:.2f}"), 0, 1)
                pdf.cell(0, 10, pdf.safe_text(f"p-value: {p_value_lag:.3f}"), 0, 1)
        
        # Удаление временных файлов
        for filename in [temp_plot1] + [f"temp_plot_lag{i}.png" for i in range(max_lag + 1)]:
            if os.path.exists(filename):
                os.remove(filename)
        
        return pdf
        
    except Exception as e:
        st.error(f"Ошибка при создании PDF: {str(e)}")
        return None

# Обновленный код для кнопки генерации PDF
if st.button("Сгенерировать PDF отчет"):
    with st.spinner("Генерация отчета..."):
        pdf = create_pdf()
        
        if pdf is not None:
            try:
                # Создаем временный файл
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    # Генерируем PDF
                    pdf_output = pdf.output(dest='S')
                    tmp.write(pdf_output.encode('latin1', 'replace'))
                    tmp_path = tmp.name
                
                # Читаем файл обратно для проверки
                with open(tmp_path, 'rb') as f:
                    pdf_bytes = f.read()
                
                # Проверяем размер файла (должен быть больше 0)
                if os.path.getsize(tmp_path) > 0:
                    st.success("PDF успешно сгенерирован!")
                    
                    # Кнопка скачивания
                    st.download_button(
                        label="Скачать PDF отчет",
                        data=pdf_bytes,
                        file_name=f"oil_cpi_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf",
                        key="unique_download_button"
                    )
                    
                    # Дополнительная проверка - показываем размер файла
                    st.info(f"Размер PDF файла: {len(pdf_bytes)/1024:.2f} KB")
                else:
                    st.error("Сгенерирован пустой PDF файл")
                
                # Удаляем временный файл
                os.unlink(tmp_path)
                
            except Exception as e:
                st.error(f"Ошибка при сохранении PDF: {str(e)}")
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    os.unlink(tmp_path)


# Отображение сырых данных
st.subheader("Исходные данные")
st.dataframe(df_filtered.style.format({
    "CPI": "{:.2f}",
    "Oil": "{:.2f}"
}))

