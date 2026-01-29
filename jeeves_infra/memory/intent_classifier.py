"""
LLM-based intent classification for memory writes.

Determines whether user input is:
- Task (actionable item)
- Journal (thought/note)
- Fact (preference/setting)
- Message (conversation)
"""

from typing import Dict, Any, List, Optional
import json
from shared import get_component_logger
from jeeves_infra.protocols import LoggerProtocol, LLMProviderProtocol



INTENT_CLASSIFICATION_PROMPT = """Analyze this user input and classify its intent.

Input: "{content}"
Context: {context}

Classify as (0.0-1.0 confidence for each):
1. Task: Actionable item with clear completion criteria (e.g., "Buy milk", "Finish report by Friday")
2. Journal: Thought, note, observation, or reflection (e.g., "Had a great day", "Feeling stressed about project")
3. Fact: Persistent preference, setting, or knowledge to remember (e.g., "I prefer dark mode", "My email is user@example.com")
4. Message: Conversational continuation (e.g., "Hello", "Thank you", "What's the weather?")

If task (confidence > 0.7):
  - Extract: title, description, due_date (if mentioned), priority (low/medium/high/urgent), tags

If journal (confidence > 0.5):
  - Extract: category (thought/observation/reflection), sentiment (positive/negative/neutral)

If fact (confidence > 0.8):
  - Extract: key (short identifier), value (the fact itself), domain (category)

Return ONLY valid JSON (no markdown, no code blocks):
{{
    "is_task": 0.0,
    "is_journal": 0.0,
    "is_fact": 0.0,
    "is_message": 0.0,
    "task_attributes": {{}},
    "journal_attributes": {{}},
    "fact_attributes": {{}}
}}"""


class IntentClassifier:
    """Classify user input intent using LLM."""

    def __init__(
        self,
        llm_provider: LLMProviderProtocol,
        model: Optional[str] = None,
        task_threshold: float = 0.7,
        journal_threshold: float = 0.5,
        fact_threshold: float = 0.8,
        logger: Optional[LoggerProtocol] = None
    ):
        """
        Initialize intent classifier.

        Args:
            llm_provider: LLM provider for classification
            model: Optional model override (uses provider default if None)
            task_threshold: Minimum confidence to classify as task
            journal_threshold: Minimum confidence to classify as journal
            fact_threshold: Minimum confidence to classify as fact

            logger: Optional logger instance (ADR-001 DI)
        """
        self.llm = llm_provider
        self.model = model
        self.task_threshold = task_threshold
        self.journal_threshold = journal_threshold
        self.fact_threshold = fact_threshold
        self._logger = get_component_logger("intent_classifier", logger)

    async def classify(
        self,
        content: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Classify content intent.

        Args:
            content: User input to classify
            context: Optional context (session info, recent messages, etc.)

        Returns:
            Classification result with confidence scores and extracted attributes
        """
        if not content or not content.strip():
            self._logger.warning("empty_content_provided")
            return self._get_default_classification()

        # Build prompt
        context_str = json.dumps(context or {}, indent=2)
        prompt = INTENT_CLASSIFICATION_PROMPT.format(
            content=content,
            context=context_str
        )

        try:
            # Call LLM
            self._logger.debug("calling_llm_for_classification", content_length=len(content))

            # Use model if specified, otherwise provider will use default
            model = self.model or "llama3.1:8b-instruct-q4_0"

            response = await self.llm.generate(
                model=model,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Low temperature for consistent classification
                    "max_tokens": 500
                }
            )

            # Parse LLM response
            classification = self._parse_llm_response(response)

            # Apply thresholds to determine primary type
            classification['primary_type'] = self._determine_primary_type(classification)

            self._logger.info(
                "classification_complete",
                content_length=len(content),
                primary_type=classification['primary_type'],
                is_task=classification['is_task'],
                is_journal=classification['is_journal'],
                is_fact=classification['is_fact'],
                is_message=classification['is_message']
            )

            return classification

        except Exception as e:
            self._logger.error("classification_failed", error=str(e), content_length=len(content))
            # Return default classification on error (assume message)
            return self._get_default_classification()

    async def classify_batch(
        self,
        contents: List[str],
        contexts: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Batch classification for efficiency.

        Args:
            contents: List of user inputs to classify
            contexts: Optional list of contexts (one per content)

        Returns:
            List of classification results
        """
        if not contents:
            return []

        # Ensure contexts match contents length
        if contexts is None:
            contexts = [{}] * len(contents)
        elif len(contexts) < len(contents):
            contexts.extend([{}] * (len(contents) - len(contexts)))

        # Classify each content
        results = []
        for content, context in zip(contents, contexts):
            result = await self.classify(content, context)
            results.append(result)

        return results

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM JSON response.

        Args:
            response: LLM response string

        Returns:
            Parsed classification dict
        """
        try:
            # Clean response (remove markdown code blocks if present)
            cleaned = response.strip()
            if cleaned.startswith('```'):
                # Remove markdown code blocks
                lines = cleaned.split('\n')
                cleaned = '\n'.join(lines[1:-1]) if len(lines) > 2 else cleaned

            # Parse JSON
            result = json.loads(cleaned)

            # Validate structure
            required_fields = ['is_task', 'is_journal', 'is_fact', 'is_message']
            for field in required_fields:
                if field not in result:
                    self._logger.warning("missing_field_in_response", field=field)
                    result[field] = 0.0

            # Ensure confidence scores are in [0, 1]
            for field in required_fields:
                value = result[field]
                if not isinstance(value, (int, float)):
                    result[field] = 0.0
                else:
                    result[field] = max(0.0, min(1.0, float(value)))

            # Ensure attribute dicts exist
            for attr_field in ['task_attributes', 'journal_attributes', 'fact_attributes']:
                if attr_field not in result:
                    result[attr_field] = {}

            return result

        except json.JSONDecodeError as e:
            self._logger.error("json_parse_failed", error=str(e), response=response[:200])
            return self._get_default_classification()
        except Exception as e:
            self._logger.error("response_parse_failed", error=str(e))
            return self._get_default_classification()

    def _determine_primary_type(self, classification: Dict[str, Any]) -> str:
        """
        Determine primary type based on confidence scores and thresholds.

        Args:
            classification: Classification result

        Returns:
            Primary type (task, journal, fact, or message)
        """
        # Check each type against threshold
        is_task = classification['is_task'] >= self.task_threshold
        is_journal = classification['is_journal'] >= self.journal_threshold
        is_fact = classification['is_fact'] >= self.fact_threshold

        # Determine primary type (highest confidence that meets threshold)
        max_score = 0.0
        primary_type = 'message'  # Default

        if is_task and classification['is_task'] > max_score:
            max_score = classification['is_task']
            primary_type = 'task'

        if is_journal and classification['is_journal'] > max_score:
            max_score = classification['is_journal']
            primary_type = 'journal'

        if is_fact and classification['is_fact'] > max_score:
            max_score = classification['is_fact']
            primary_type = 'fact'

        return primary_type

    def _get_default_classification(self) -> Dict[str, Any]:
        """
        Get default classification (for errors or empty input).

        Returns:
            Default classification (message type with 1.0 confidence)
        """
        return {
            'is_task': 0.0,
            'is_journal': 0.0,
            'is_fact': 0.0,
            'is_message': 1.0,
            'task_attributes': {},
            'journal_attributes': {},
            'fact_attributes': {},
            'primary_type': 'message'
        }
