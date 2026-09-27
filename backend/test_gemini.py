from .gemini import get_gemini_client


def main():
    client = get_gemini_client()
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents="Say hello in one sentence",
    )
    print(response.text)


if __name__ == "__main__":
    main()
