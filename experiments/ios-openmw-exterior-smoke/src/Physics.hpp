#pragma once
#include <components/resource/bulletshape.hpp>
#include <osg/Matrix>
#include <osg/Vec3d>
#include <btBulletDynamicsCommon.h>
#include <BulletCollision/CollisionDispatch/btGhostObject.h>
#include <BulletDynamics/Character/btKinematicCharacterController.h>
#include <memory>
#include <vector>

namespace G3 {
static_assert(sizeof(btScalar)==sizeof(double),"G3 requires the verified double-precision Bullet ABI");
// Own the NifBullet templates as well as instances: the latter share mesh data.
class Physics {
    btDefaultCollisionConfiguration config;
    btCollisionDispatcher dispatcher{&config};
    btDbvtBroadphase broadphase;
    btSequentialImpulseConstraintSolver solver;
    btDiscreteDynamicsWorld world{&dispatcher,&broadphase,&solver,&config};
    btGhostPairCallback pairs;
    std::vector<std::shared_ptr<const Resource::BulletShape>> templates;
    std::vector<std::shared_ptr<Resource::BulletShapeInstance>> shapes;
    std::vector<std::unique_ptr<btCollisionObject>> objects;
    std::vector<Resource::CollisionShapePtr> terrain;
    btCapsuleShapeZ capsule{16,64};
    btPairCachingGhostObject ghost;
    btKinematicCharacterController character{&ghost,&capsule,20,btVector3(0,0,1)};
    double accumulator=0;
public:
    static constexpr double FixedStep=1./120;
    static constexpr double MaxFrameDelta=.25;
    static constexpr unsigned MaxFrameSteps=30;
    unsigned collisionless=0;
    unsigned long long steps=0;
    double droppedSeconds=0;
    Physics();
    ~Physics();
    Physics(const Physics&)=delete;
    Physics& operator=(const Physics&)=delete;
    void add(std::shared_ptr<const Resource::BulletShape> source,const osg::Matrix& matrix);
    void addTerrain(Resource::CollisionShapePtr shape);
    void start(const osg::Vec3d& feet);
    osg::Vec3d move(const osg::Vec3d& velocity,double dt);
    bool grounded() const{return character.onGround();}
    void jump(){if(character.onGround())character.jump(btVector3(0,0,270));}
    unsigned objectCount() const{return objects.size();}
};
}
