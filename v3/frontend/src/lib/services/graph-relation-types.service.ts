import { ApiService, type ApiOptions, type RequestResponse } from './api.service';
import type { GraphRelationType, GraphRelationTypeInput } from '$lib/types/resources/case-graph';

const RELATION_TYPES_PATH = '/manage/graph-relation-types';

export class GraphRelationTypesService {
	static listRelationTypes(
		options: ApiOptions = {}
	): Promise<RequestResponse<GraphRelationType[]>> {
		return ApiService.get<GraphRelationType[]>(RELATION_TYPES_PATH, options);
	}

	static createRelationType(
		body: GraphRelationTypeInput,
		options: ApiOptions = {}
	): Promise<RequestResponse<GraphRelationType>> {
		return ApiService.post<GraphRelationType>(RELATION_TYPES_PATH, body, options);
	}

	static updateRelationType(
		relationTypeId: number,
		body: GraphRelationTypeInput,
		options: ApiOptions = {}
	): Promise<RequestResponse<GraphRelationType>> {
		return ApiService.put<GraphRelationType>(
			`${RELATION_TYPES_PATH}/${relationTypeId}`,
			body,
			options
		);
	}

	/** 400 when the type is in use; system types cannot be deleted. */
	static deleteRelationType(
		relationTypeId: number,
		options: ApiOptions = {}
	): Promise<RequestResponse<null>> {
		return ApiService.delete<null>(`${RELATION_TYPES_PATH}/${relationTypeId}`, options);
	}

	static reorderRelationTypes(
		ids: number[],
		options: ApiOptions = {}
	): Promise<RequestResponse<GraphRelationType[]>> {
		return ApiService.post<GraphRelationType[]>(`${RELATION_TYPES_PATH}/reorder`, { ids }, options);
	}

}
