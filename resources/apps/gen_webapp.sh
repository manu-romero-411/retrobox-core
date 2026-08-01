#!/usr/bin/env bash
# gen_webapps.sh
# Genera archivos .webapp/.kodi y gamelist.xml para servicios de streaming
# Ejecutar desde el directorio donde quieras los archivos de salida

set -uo pipefail

DESTINO="${1:-.}"
ICONS_DIR="${DESTINO}/app-icons"

mkdir -p "$DESTINO"
mkdir -p "$ICONS_DIR"

# Definición de servicios
# Formato: "id|nombre|url|desarrollador|descripción|fecha(YYYYMMDD)|extensión"

declare -a SERVICIOS=(
    "youtube|YouTube|https://www.youtube.com|Google LLC|Plataforma de vídeo online con millones de vídeos subidos por usuarios y creadores de todo el mundo.|20050214|webapp"
    "twitch|Twitch|https://www.twitch.tv|Twitch Interactive|Plataforma líder de streaming en directo, centrada en videojuegos, esports y contenido creativo.|20110606|webapp"
    "rtve_play|RTVE Play|https://www.rtve.es/play/|RTVE|Servicio de streaming gratuito de Radio Televisión Española con acceso a series, películas, noticias y contenido en directo.|20110101|webapp"
    "atresplayer|Atresplayer|https://www.atresplayer.com|Atresmedia|Plataforma de streaming de Atresmedia con contenido de Antena 3, laSexta y canales temáticos, incluyendo series exclusivas.|20120901|webapp"
    "spotify|Spotify|https://open.spotify.com|Spotify AB|Servicio de música en streaming con acceso a millones de canciones, podcasts y listas de reproducción personalizadas.|20081007|webapp"
    "pluto_tv|Pluto TV|https://pluto.tv|Paramount Streaming|Servicio gratuito de streaming con publicidad que ofrece canales lineales temáticos y contenido bajo demanda sin necesidad de registro.|20140331|webapp"
    "crunchyroll|Crunchyroll|https://www.crunchyroll.com|Sony Pictures Entertainment|Plataforma especializada en anime, manga y dorama con el mayor catálogo de animación japonesa en streaming del mundo.|20060514|webapp"
    "kodi|Kodi|kodi|Kodi Foundation|Centro multimedia de código abierto para reproducir vídeo, música, imágenes y podcasts desde cualquier fuente local o en red.|20040101|kodi"
    "amazon_prime_video|Amazon Prime Video|https://www.primevideo.com|Amazon.com Inc.|Servicio de streaming de Amazon con películas, series originales y eventos deportivos en directo incluido con Prime.|20060907|webapp"
    "hbo_max|Max (HBO Max)|https://www.max.com|Warner Bros. Discovery|Plataforma de streaming de Warner Bros. Discovery con contenido de HBO, DC, Cartoon Network y producciones originales exclusivas.|20200527|webapp"
    "netflix|Netflix|https://www.netflix.com|Netflix Inc.|El mayor servicio de streaming del mundo, con series, películas y documentales originales disponibles en más de 190 países.|20070116|webapp"
)

# Generar archivos .webapp / .kodi

echo "Generando archivos de rom..."

for entrada in "${SERVICIOS[@]}"; do
    IFS='|' read -r id nombre url dev desc fecha ext <<< "$entrada"

    archivo="${DESTINO}/${id}.${ext}"
    echo "$url" > "$archivo"
    echo "  ✔ ${id}.${ext}"
done

# Generar gamelist.xml

echo ""
echo "Generando gamelist.xml..."

GAMELIST="${DESTINO}/gamelist.xml"

cat > "$GAMELIST" << 'XMLHEADER'
<?xml version="1.0" encoding="UTF-8"?>
<gameList>
XMLHEADER

for entrada in "${SERVICIOS[@]}"; do
    IFS='|' read -r id nombre url dev desc fecha ext <<< "$entrada"

    # Formatear fecha como YYYYMMDDTHHMMSS
    fecha_fmt="${fecha}T000000"
    icon_path="./app-icons/${id}.png"

    cat >> "$GAMELIST" << XMLENTRY
	<game>
		<path>./${id}.${ext}</path>
		<name>${nombre}</name>
		<desc>${desc}</desc>
		<image>${icon_path}</image>
		<marquee>${icon_path}</marquee>
		<rating>0</rating>
		<releasedate>${fecha_fmt}</releasedate>
		<developer>${dev}</developer>
		<publisher>${dev}</publisher>
		<genre>Streaming</genre>
		<playcount />
		<lastplayed />
		<gametime />
		<lang>es</lang>
		<region>wr</region>
	</game>
XMLENTRY

    echo "  ✔ entrada XML: ${nombre}"
done

cat >> "$GAMELIST" << 'XMLFOOTER'
</gameList>
XMLFOOTER

# Resumen

echo ""
echo "══════════════════════════════════════════════"
echo "  ✔  Archivos generados en: ${DESTINO}"
echo "  ✔  gamelist.xml creado"
echo ""
echo "  Iconos esperados en ${ICONS_DIR}/:"
for entrada in "${SERVICIOS[@]}"; do
    IFS='|' read -r id nombre url dev desc fecha ext <<< "$entrada"
    echo "     • ${id}.png"
done
echo "══════════════════════════════════════════════"
echo ""
