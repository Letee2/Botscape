rule Telegram_Bot_Token_Hunter {
    meta:
        author = "Letee2"
        description = "Detects Telegram Bot tokens, API URLs and common libraries with obfuscation awareness"
        severity = "High"
        date = "2025-12-11"

    strings:
        // --- Patrón Base del Token ---
        // Estructura: 8-10 digitos, dos puntos, 35 caracteres alfanuméricos
        $token_pattern = /\d{8,10}:[a-zA-Z0-9_-]{35}/ ascii wide

        // --- Indicadores de Infraestructura (API URL) ---
        $api_url_1 = "api.telegram.org" ascii wide nocase
        $api_url_2 = "core.telegram.org" ascii wide nocase
        
        // --- Base64 de api.telegram.org ---
        $b64_url_1 = "YXBpLnRlbGVncmFtLm9yZw" ascii wide // api.telegram.org
        $b64_url_2 = "Ym90" ascii wide // "bot" (parte de /bot<token>)

        // --- Stack Strings / Ofuscación común ---
        // Intento de detectar 'a', 'p', 'i', '.', 't'... separados por null bytes o basura (wide/stack)
        $stack_api = { 61 00 ?? 00 70 00 ?? 00 69 00 ?? 00 2E } 
        
        // --- Librerías comunes (Python/C#/Go) ---
        $lib_1 = "python-telegram-bot" ascii wide nocase
        $lib_2 = "Telethon" ascii wide nocase
        $lib_3 = "aiogram" ascii wide nocase
        $lib_4 = "Telegram.Bot" ascii wide nocase // C#

    condition:
        // 1. Token explícito (Regex directo)
        $token_pattern or 
        
        // 2. Infraestructura (URL normal O Stack String) + Librería
        ((any of ($api_url*) or $stack_api) and any of ($lib*)) or
        
        // 3. Infraestructura ofuscada (Base64) + Librería
        (any of ($b64_url*) and any of ($lib*))
}