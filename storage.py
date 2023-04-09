import os.path
from typing import Optional

import faiss
import numpy as np
import pandas as pd
from pgvector.sqlalchemy import Vector

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from abc import ABC, abstractmethod

from config import Config

Base = declarative_base()


class Storage(ABC):
    """Abstract Storage class."""

    # factory method
    @staticmethod
    def create_storage(cfg: Config, filename: Optional[str] = None) -> 'Storage':
        """Create a storage object."""
        if cfg.use_postgres:
            return _PostgresStorage(cfg)
        else:
            return _IndexStorage(filename=filename)

    @abstractmethod
    def add(self, text: str, embedding: list[float], filename: str):
        """Add a new embedding."""
        pass

    @abstractmethod
    def add_all(self, embeddings: list[tuple[str, list[float]]], filename: str):
        """Add multiple embeddings."""
        pass

    @abstractmethod
    def get_texts(self, embedding: list[float], limit=100) -> list[str]:
        """Get the text for the provided embedding."""
        pass

    @abstractmethod
    def clear(self, filename: str):
        """Clear the database."""
        pass


class _IndexStorage(Storage):
    """IndexStorage class."""

    def __init__(self, filename=None):
        """Initialize the storage."""
        self.texts = None
        self.index = None
        self._load(filename)

    def add(self, text: str, embedding: list[float], filename: str):
        """Add a new embedding."""
        array = np.array([embedding])
        self.texts = pd.concat([self.texts, pd.DataFrame({'index': len(self.texts), 'text': text}, index=[0])])
        self.index.add(array)
        self._save(filename)

    def add_all(self, embeddings: list[tuple[str, list[float]]], filename: str):
        """Add multiple embeddings."""
        self.texts = pd.concat([self.texts, pd.DataFrame(
            {'index': len(self.texts) + i, 'text': text} for i, (text, _) in enumerate(embeddings))])
        array = np.array([emb for text, emb in embeddings])
        self.index.add(array)
        self._save(filename)

    def get_texts(self, embedding: list[float], limit=10) -> list[str]:
        _, indexs = self.index.search(np.array([embedding]), limit)
        return self.texts.iloc[indexs[0]].text.tolist()

    def clear(self, filename: str):
        """Clear the database."""
        self._delete(filename)

    def _save(self, filename: str):
        self.texts.to_csv(f"{filename}.csv")
        faiss.write_index(self.index, f"{filename}.bin")

    def _load(self, filename: str):
        if os.path.exists(filename + '.csv') and os.path.exists(filename + '.bin'):
            self.texts = pd.read_csv(filename + '.csv')
            self.index = faiss.read_index(filename + '.bin')
        else:
            self.texts = pd.DataFrame(columns=['index', 'text'])
            self.index = faiss.IndexFlatIP(1536)

    def _delete(self, filename: str):
        try:
            os.remove(filename + '.csv')
            os.remove(filename + '.bin')
        except FileNotFoundError:
            pass
        # self._load(filename)


class _PostgresStorage(Storage):
    """PostgresStorage class."""

    def __init__(self, cfg: Config):
        """Initialize the storage."""
        self._postgresql = cfg.postgres_url
        self._engine = create_engine(self._postgresql)
        Base.metadata.create_all(self._engine)
        session = sessionmaker(bind=self._engine)
        self._session = session()

    def add(self, text: str, embedding: list[float], filename: str):
        """Add a new embedding."""
        self._session.add(EmbeddingEntity(text=text, embedding=embedding))
        self._session.commit()

    def add_all(self, embeddings: list[tuple[str, list[float]]], filename: str):
        """Add multiple embeddings."""
        data = [EmbeddingEntity(text=text, embedding=embedding) for text, embedding in embeddings]
        self._session.add_all(data)
        self._session.commit()

    def get_texts(self, embedding: list[float], limit=100) -> list[str]:
        """Get the text for the provided embedding."""
        result = self._session.query(EmbeddingEntity).order_by(
            EmbeddingEntity.embedding.cosine_distance(embedding)).limit(limit).all()
        return [s.text for s in result]

    def clear(self):
        """Clear the database."""
        self._session.query(EmbeddingEntity).delete()
        self._session.commit()

    def __del__(self):
        """Close the session."""
        self._session.close()


class EmbeddingEntity(Base):
    __tablename__ = 'embedding'
    id = Column(Integer, primary_key=True)
    text = Column(String)
    embedding = Column(Vector(1536))
