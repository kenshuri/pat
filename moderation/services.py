from moderation.models import ModerationResult
from mistralai import Mistral
import os

def moderate_text(text: str) -> ModerationResult:
    api_key = os.getenv('MISTRAL_API_KEY')
    client = Mistral(api_key=api_key)

    try:
        response = client.classifiers.moderate(
            model="mistral-moderation-latest",
            inputs=[text]
        )
        failed_categories = []
        for result in response.results:
            failed_categories = [
                category for category, flagged in result.categories.items() if flagged
            ]
        return ModerationResult.objects.create(
            passed=len(failed_categories) == 0,
            reasons=", ".join(failed_categories)
        )
    except Exception as e:
        return ModerationResult.objects.create(
            passed=False,
            reasons="api_error"
        )

