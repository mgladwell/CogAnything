# Import things that are needed
#pip install langchain, pydantic, requests, gradio, azure-ai-textanalytics==5.2.0, openai 

import uuid
from langchain.agents import AgentType, initialize_agent
from langchain.llms import AzureOpenAI
from langchain.tools import BaseTool
from typing import List, Type
import os
from pydantic import BaseModel, Field
import requests
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
import gradio as gr
import re

## ENTER IN HERE:
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_API_BASE"] = ""
os.environ["OPENAI_API_VERSION"] = ""
os.environ["OPENAI_API_TYPE"] = ""

API_KEY = ""
DEPLOYMENT_NAME = ""

## CogServices
subscription_key = ""
endpoint = ""

## Translate
subscription_key_translate = ""
region = ""
client_trace_id = str(uuid.uuid4())


## Using the AzureChatOpenAI
class NewAzureOpenAI(AzureOpenAI):
    stop: List[str] = None
    @property
    def _invocation_params(self):
        params = super()._invocation_params
        # fix InvalidRequestError: logprobs, best_of and echo parameters are not available on gpt-35-turbo model.
        params.pop('logprobs', None)
        params.pop('best_of', None)
        params.pop('echo', None)
        #params['stop'] = self.stop
        return params

# Creating the LLM for Agent
llm = NewAzureOpenAI(deployment_name="chat", model_name=DEPLOYMENT_NAME )

#Set up CogServices
def authenticate_client():
    ta_credential = AzureKeyCredential(subscription_key)
    text_analytics_client = TextAnalyticsClient(
            endpoint=endpoint, 
            credential=ta_credential)
    return text_analytics_client

client = authenticate_client()

###### TOOLS FOR COGSERVICES #######
## EntityRecognition
class EntityRecognitionInput():
    documents: dict = Field()

class AzureEntityRecognitionTool(BaseTool):
    name = "EntityRecognition"
    description = "useful for recognizing entities in text."
    args_schema: Type[BaseModel] = EntityRecognitionInput

    def _run(self, text: dict, clients = client) -> dict:
        """Use the tool."""
        try:
            documents = [text]
            response = client.extract_key_phrases(documents = documents)[0]
            return response

        except Exception as err:
            print("Encountered exception. {}".format(err))

    async def _arun(self, documents: dict) -> dict:
        """Use the tool asynchronously."""
        raise NotImplementedError("AzureEntityRecognition does not support async")

azure_entity_recognition_tool = AzureEntityRecognitionTool()

#Language Dectection
class LanguageDetectionInput(BaseModel):
    text: str = Field()

class AzureLanguageDetectionTool(BaseTool):
    name = "LanguageDetection"
    description = "useful for dectecting the language of the input text"
    args_schema: Type[BaseModel] = LanguageDetectionInput

    def _run(self, text: str) -> dict:
        try:
            documents = [text]
            response = client.detect_language(documents = documents, country_hint = 'us')[0]
            return response
        except Exception as err:
            print("Encountered exception. {}".format(err))

    async def _arun(self, text: str) -> dict:
        """Use the tool asynchronously."""
        raise NotImplementedError("AzureLanguageDetection does not support async")


azure_language_detection_tool = AzureLanguageDetectionTool()

## Key Phrase Extraction
class KeyPhraseExtractionInput():
    documents: dict = Field()

class AzureKeyPhraseExtractionTool(BaseTool):
    name = "KeyPhraseExtraction"
    description = "useful for extracting key phrases in text"
    args_schema: Type[BaseModel] = KeyPhraseExtractionInput

    def _run(self, text: dict) -> dict:
        """Use the tool."""
        try:
            documents = [text]
            response = client.extract_key_phrases(documents = documents)[0]
            return response

        except Exception as err:
            print("Encountered exception. {}".format(err))

    async def _arun(self, documents: dict) -> dict:
        """Use the tool asynchronously."""
        raise NotImplementedError("AzureKeyPhraseExtraction does not support async")

azure_key_phrase_extraction_tool = AzureKeyPhraseExtractionTool()

## Sentiment Analysis
class SentimentAnalysisInput():
    documents: dict = Field()

class AzureSentimentAnalysisTool(BaseTool):
    name = "SentimentAnalysis"
    description = "useful for anaylsing sentiment in text. Consider the weights of the individual sentiment "
    args_schema: Type[BaseModel] = SentimentAnalysisInput

    def _run(self, text: dict) -> dict:
        documents = [text] 
        result = client.analyze_sentiment(documents, show_opinion_mining=True)
        return result

    async def _arun(self, documents: dict) -> dict:
        """Use the tool asynchronously."""
        raise NotImplementedError("AzureSentimentAnalysis does not support async")

azure_sentiment_analysis_tool = AzureSentimentAnalysisTool()


# Text Translation
class TextTranslationInput(BaseModel):
    text: str = Field()

class AzureTextTranslationTool(BaseTool):
    name = "TextTranslation"
    description = "useful for translating text into English."
    args_schema: Type[BaseModel] = TextTranslationInput

    def _run(self, text: str) -> dict:
        url = f"https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&to=en"
        headers = {
                "Ocp-Apim-Subscription-Key": subscription_key_translate,
                "Content-Type": "application/json",
                "Ocp-Apim-Subscription-Region": region,
                'X-ClientTraceId': str(uuid.uuid4())
                }
        body = [{"text": text}]
        response = requests.post(url, headers=headers, json=body)
        response_json = response.json()
        return response_json

    async def _arun(self, text: str) -> dict:
        """Use the tool asynchronously."""
        raise NotImplementedError("AzureTextTranslation does not support async")

azure_text_translation_tool = AzureTextTranslationTool()


#Tools that the LLM has access to
tools = [
    azure_entity_recognition_tool,
    azure_language_detection_tool,
    azure_key_phrase_extraction_tool,
    azure_sentiment_analysis_tool,
    azure_text_translation_tool]


#Creating the Agent
agent = initialize_agent(tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True)


#Pre-prompt Template
template =  """I want you to be CogAnything. An agent that uses a mixture of Azure CogServices to get answers. You are reliable and trustworthy.

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of the tools. 
Action Input: the input to the action
Observation: the result of the action
Thought: you should always think about what to do next. Use the Observation to gather extra information, but never use information outside of the Observation.
Action: the action to take, should be one of the tools. 
Action_input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer.
Final Answer: the final answer to the original input question. Do not give a question after. 

After the Final Answer, do not return anything else.
Begin!
"""

#Function to work with Gradio

#Demo Example. 
def extract_final_answer(text):
    match = re.search(r'Final Answer:(.*?)(\n|$)', text)
    if match:
        return match.group(1).strip()
    return "Final Answer not found."

def start(text):
    output = agent.run(template + text)
    final_answer = extract_final_answer(output)
    return final_answer

demo = gr.Interface(fn = start, inputs = gr.Textbox(lines=2, placeholder= "Ask me Anything!"), outputs = gr.Textbox(lines=2))
demo.launch()


