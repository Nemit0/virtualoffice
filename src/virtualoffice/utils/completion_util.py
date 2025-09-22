import os
from openai import OpenAI

from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_text(prompt:  list[dict], model: str = "gpt-3.5-turbo") -> tuple[str, int]:
    response = client.chat.completions.create(
        model=model,
        messages=prompt
    )
    return response.choices[0].message.content, response.usage.total_tokens

if __name__ == "__main__":
    print(client.models.list())
    print(client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": "Hello!"},
        ]
    ))
    print("Done")