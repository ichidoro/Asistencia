import subprocess
import sys
import json

def main():
    print("Iniciando despliegue con recuperación de variables de entorno...")
    
    # Env vars parsed from successful revision asistencia-aguacol-00165-zrt
    env_vars = {
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "ALGORITHM": "HS256",
        "API_RELOAD": "false",
        "APP_ENV": "production",
        "CONTROL_ASISTENCIA_PASSWORD": "123456",
        "CONTROL_ASISTENCIA_URL": "https://bioalba1.controlasistencia.cl",
        "CONTROL_ASISTENCIA_USER": "aguacol",
        "DEBUG": "false",
        "EMAIL_FROM": "operaciones.aguacol.spa@gmail.com",
        "FEATURE_EXPORTAR_PDF": "true",
        "FEATURE_NOTIFICACIONES_EMAIL": "true",
        "LOG_LEVEL": "INFO",
        "SCRAPER_ENABLED": "true",
        "SECRET_KEY": "f6f0eba50b84406b6a1c7903dd4eb123f22fb97584020c5174878494b0a6dcbd",
        "SMTP_PASSWORD": "erff ayax grfd umvj",
        "SMTP_PORT": "587",
        "SMTP_SERVER": "smtp.gmail.com",
        "SMTP_USER": "operaciones.aguacol.spa@gmail.com",
        "TIMEZONE": "America/Santiago",
        "TURSO_AUTH_TOKEN": "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODAwMjM1MzUsImlkIjoiMDE5ZTcxYWItOGYwMS03NWVkLWJmMDMtMDExZjk5MjE3ZWM4IiwicmlkIjoiZmE1OTYxZWYtNDEwOS00MTY1LTkwMzMtNzA4YmI5MzNiNjkwIn0.S3g__Bhy2on3tw8xzTugeFaGR-gNlz5D0Mcg-DAStaJQ_83qgLmllMZy-n5WjANJz-oTNok6h75XY1bHCmQJDg",
        "TURSO_DATABASE_URL": "libsql://aguacol-ichidoro.aws-us-east-1.turso.io",
        "CRON_SECRET": "mi-super-secreto-compartido-para-sincronizacion-auto-123",
        "GOOGLE_DRIVE_FOLDER_ID": "1Y3YeLP9l1O5IZdLVlvCDqUjfLRehv_Rp",
        "GOOGLE_APPLICATION_CREDENTIALS_JSON": "{\"type\": \"service_account\", \"project_id\": \"asistencia-13c58\", \"private_key_id\": \"230b9fe62f7013d0cfcc6e3e8f7c5bae7e4d8efe\", \"private_key\": \"-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDy7zpzHHByqHvz\\nT1wEDP9T20fcTCV450Hn8/t3qWGTyZ/h7rXXBGzm8zTWulZOzCuFvnIhEJZA49kt\\nenEGZ6wHNh5yhOL1Xu+qPJU/G/x6L/rspaS1SBD2wBxnUwbgJjHhCIyGKvLl8w+B\\nkhY5SxBhawDq9QDCa63dZ+W4+jeVbIXqrpci/OihzVJg5+j47fOcwz6T8J6oIjba\\n07wXvn7RwJ/PT6+eR7VyYAuQf9haYn8iu8DwFRvPNi51afbd5TbHpJ5Iz9HzwJv8\\nRPpPTeX8UFJ2WltoNtZk1Vc+auTXxkiaDEb4yz37YgUsjypDghXhfMXc2sxfxrGk\\nkY55iWt1AgMBAAECggEAKUDYox2MNtxHmCy8ym9OmHXfQRipMFvNBE+ZP1vDFy6g\\n+OPpeybkO1/HdENWTrE7Hs4VYWoIqeJHSgLF2LmYK+1TxEyuoc5KUpVRHtNoz3MA\\nYFlMnAAt6Uj8Sct+mmfCBp3GBy6Z6tSYqH8fSQFnObPLBxst0tYoQzXWe8/5ymS7\\nqwMIQBjzHbqA2DklHWRAA7VUaWeB7rAVUIFmpHjM5SjX/swwTfRrkv6mx6FEG/CM\\nLiCsrPnkmbJhUHVFkjs/t7KMd1WW8XuMiDsHS3OByLParatWnQk51x/PYZ7F/c2i\\n/l17YSLlzAwfjczL+T9QDNcg22VyhWDS+qeCrE/MYQKBgQD/+8jrRHyiImuHH3zv\\n9oqMYOgoWEg0JNkdT7Mrd6GzqqdVKLRY4hkniCSKJGJg36Ox1y7GtcxAwG7a3sAo\\nFaNlsXlasyaRmVLViLJKUxztgUYkGR+gQjQ09kGNU39eyOOG8XjymM5g0zrWUzN8\\n8tb9u+1ioi7cDqG50UhBVNyqTQKBgQDy8zqF9Q/4UWKEUhhiX6JItbe0nVSQAM/3\\nUxNVt7/UhA9OBHpH/KR6d8mZnW6yOWy/YsOXTMn1RH2xmvlxfmAujINckYrVx2Ht\\np1EYChzWbnFFigQL5z0nKcKuHsPgH97Zw/vuEQkC0GAlw8ARMWaVq54GQxtSLPPq\\n4vxw3vcJyQKBgCC1VWjqaVp2N3MejOJEiFODlmaBUUiIZM2f/27QbHL+nT7+Ynzw\\n9vHcLX8RQxjJuqrgqfNuC1lCvWduCvOUQDqgQLdcKNN12eW6/70LfajDWekG5Mmf\\na/hQdvPN9XpxBNGbTS8CY2xv0RbNrsiKZvoo5x4xRveLTxLlMOxYIZIJAoGBAO+M\\n/KuRE4oZVTZ7bCezfGSNKPIiH3tOEcEgXPQsFi4JeL3IlHnelp9a9aFOJhP9o0ii\\nrZDF2mzId9djo4lQvq2nRu9DYs2fpuOaEs/NSNn2VCHpEExcWWQAPUFKfIDFbAr0\\nv7fhfC0WIXebKArL1wbFDS/Hg2znfiqgXaE9eABhAoGATrIOyRdTkAI1rUv1oYEa\\npIh0+yeiaeVblKNGXSx9nI1d4/xcek2RG6zQRpiGtGridU6Gus4ovSzrFWAFo51A\\nyHBBllTPdlaAhQMMjxE2DwaMjIqNHdDRZi3u1aqQ2bDUgg44hrQFwRycvmY8PFHB\\njVOwrBaudAbRGYlHfd0IUSo=\\n-----END PRIVATE KEY-----\\n\", \"client_email\": \"drive-uploader-porteria-180@asistencia-13c58.iam.gserviceaccount.com\", \"client_id\": \"106893706699443141859\", \"auth_uri\": \"https://accounts.google.com/o/oauth2/auth\", \"token_uri\": \"https://oauth2.googleapis.com/token\", \"auth_provider_x509_cert_url\": \"https://www.googleapis.com/oauth2/v1/certs\", \"client_x509_cert_url\": \"https://www.googleapis.com/robot/v1/metadata/x509/drive-uploader-porteria-180%40asistencia-13c58.iam.gserviceaccount.com\", \"universe_domain\": \"googleapis.com\"}"
    }

    # Construct the --set-env-vars string
    # We will use the custom delimiter ^|^ for gcloud to prevent any issues with special chars
    cmd = [
        "gcloud", "run", "deploy", "asistencia-aguacol",
        "--source", ".",
        "--region", "us-central1",
        f"--set-env-vars=^|^" + "|".join([f"{k}={v}" for k, v in env_vars.items()]),
        "--allow-unauthenticated"
    ]
    
    print("Ejecutando 'gcloud run deploy' con variables de entorno...")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", shell=True)
    
    print("--- STDOUT ---")
    print(result.stdout)
    
    print("--- STDERR ---")
    print(result.stderr)
    
    if result.returncode == 0:
        print("Despliegue completado exitosamente!")
    else:
        print(f"Error en despliegue. Codigo: {result.returncode}")
        sys.exit(result.returncode)

if __name__ == "__main__":
    main()
