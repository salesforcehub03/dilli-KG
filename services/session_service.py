from datetime import datetime
from flask import session

class SessionService:
    @staticmethod
    def _init_session():
        if 'visited_drugs' not in session:
            session['visited_drugs'] = []
        if 'chat_history' not in session:
            session['chat_history'] = []
        if 'viewed_nodes' not in session:
            session['viewed_nodes'] = []
        if 'session_start' not in session:
            session['session_start'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def add_visit(cls, drug_name):
        if not drug_name:
            return
            
        cls._init_session()
        visited = session['visited_drugs']
        
        # Avoid duplicates in immediate succession
        if visited and visited[-1]["name"] == drug_name:
            return

        visited.append({
            "name": drug_name,
            "time": datetime.now().strftime("%H:%M:%S")
        })
        session['visited_drugs'] = visited # ensure modified list is saved

    @classmethod
    def add_node_view(cls, node_type, label, properties):
        cls._init_session()
        viewed = session['viewed_nodes']
        viewed.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": node_type,
            "label": label,
            "properties": properties
        })
        session['viewed_nodes'] = viewed

    @classmethod
    def add_chat(cls, drug, question, answer):
        cls._init_session()
        chat = session['chat_history']
        chat.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "drug": drug,
            "question": question,
            "answer": answer
        })
        session['chat_history'] = chat

    @classmethod
    def get_session_data(cls):
        cls._init_session()
        return {
            "start_time": session['session_start'],
            "drugs": session['visited_drugs'],
            "chat": session['chat_history'],
            "viewed_nodes": session['viewed_nodes'],
            "total_visited": len(session['visited_drugs'])
        }

    @classmethod
    def clear_session(cls):
        session['visited_drugs'] = []
        session['chat_history'] = []
        session['viewed_nodes'] = []
        session['session_start'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Removing global instance; utilize class methods that back to Flask `session` context
session_manager = SessionService

