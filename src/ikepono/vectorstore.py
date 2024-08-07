import numpy as np
import faiss
from typing import List, Tuple, Dict, Any
from typing import Iterable as Iter
from ikepono.labeledimageembedding import LabeledImageEmbedding


class VectorStore:
    def __init__(self, dimension: int):
        self.dimension: int = dimension
        self.base_index: faiss.IndexFlatL2 = faiss.IndexFlatL2(dimension)
        self.index: faiss.IndexIDMap = faiss.IndexIDMap(self.base_index)
        self.id_counter: int = 0
        self.id_to_label: Dict[int, Any] = {}
        self.id_to_source: Dict[int, str] = {}
        self.label_to_ids: Dict[str, List[int]] = {}
        self.source_to_id: Dict[str, int] = {}
        self.vector_store: Dict[int, np.ndarray] = {}  # Store vectors separately

    def _add_vector(self, vector: np.ndarray, label: str, source: str) -> None:
        vector_id: int = self.id_counter
        vector_array = np.array([vector]).astype('float32')
        if label not in self.label_to_ids:
            self.label_to_ids[label] = []
        self.label_to_ids[label].append(vector_id)
        ids = np.array([vector_id]).astype('int64')
        assert vector_array.shape[0] == ids.shape[0], "Vector and ID shapes do not match: {} vs {}".format(vector_array.shape, ids.shape)
        self.index.add_with_ids(vector_array, ids)
        self.id_to_label[vector_id] = label
        self.id_to_source[vector_id] = source
        self.source_to_id[source] = vector_id
        self.vector_store[vector_id] = vector  # Store the vector
        self.id_counter += 1


    def add_labeled_image_vectors(self, livs : Iter[LabeledImageEmbedding]) -> None:
        for liv in livs:
            self._add_vector(liv.embedding, liv.label, liv.source)

    def update_vector(self, source: str, new_vector: np.ndarray, new_label: Any = None) -> None:
        if source in self.source_to_id:
            vector_id: int = self.source_to_id[source]
            old_label: Any = self.id_to_label[vector_id]

            # Update vector in FAISS and our separate storage
            self.index.remove_ids(np.array([vector_id]))
            self.index.add_with_ids(np.array([new_vector]).astype('float32'), np.array([vector_id]))
            self.vector_store[vector_id] = new_vector

            # Update label if necessary
            if new_label is not None and new_label != old_label:
                self.id_to_label[vector_id] = new_label
                self.label_to_ids[old_label].remove(vector_id)
                self.label_to_ids.setdefault(new_label, []).append(vector_id)
        else:
            raise ValueError(f"Source '{source}' not found in the store.")


    def get_vector(self, source: str) -> np.ndarray:
        if source in self.source_to_id:
            vector_id: int = self.source_to_id[source]
            return self.vector_store[vector_id]
        else:
            raise ValueError(f"Source '{source}' not found in the store.")

    def get_vectors_by_label(self, label: Any) -> np.ndarray:
        if label in self.label_to_ids:
            vectors = [self.vector_store[vector_id] for vector_id in self.label_to_ids[label]]
            return np.array(vectors)
        else:
            return np.ndarray([])

    def get_sources_by_label(self, label: Any) -> np.ndarray:
        if label in self.label_to_ids:
            sources = [self.id_to_source[vector_id] for vector_id in self.label_to_ids[label]]
            return np.array(sources)
        else:
            return np.ndarray([])

    def get_all_vectors(self) -> np.ndarray:
        if len(self.vector_store) == 0:
            return np.empty((0, self.dimension), dtype=np.float32)
        else:
            return np.stack(list(self.vector_store.values()))

    def get_all_labels(self) -> np.ndarray:
        if len(self.label_to_ids) == 0:
            return np.ndarray([])
        else:
            return np.stack(list(self.label_to_ids.keys()))

    def get_all_sources(self) -> np.ndarray:
        if len(self.source_to_id) == 0:
            return np.ndarray([])
        else:
            return np.stack(list(self.source_to_id.keys()))

    def compute_distances(self, query_vector: np.ndarray, vectors: np.ndarray) -> np.ndarray:
        return np.linalg.norm(vectors - query_vector, axis=1)

    def search(self, query_vector: np.ndarray, k: int) -> List[Tuple[float, Any, str]]:
        all_vectors = self.get_all_vectors()
        distances = self.compute_distances(query_vector, all_vectors)
        indices = np.argsort(distances)[:k]
        return [(distances[i], self.id_to_label[i], self.id_to_source[i]) for i in indices]