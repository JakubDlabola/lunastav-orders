FROM python:3.12-slim

# LibreOffice for docx → pdf conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install Arial and Times New Roman so LibreOffice renders the template correctly
RUN mkdir -p /usr/share/fonts/truetype/msfonts \
    && cp fonts/*.ttf /usr/share/fonts/truetype/msfonts/ \
    && fc-cache -f

# LibreOffice needs a writable home directory
ENV HOME=/tmp

EXPOSE 8000
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
